"""Unit tests for the ML pipeline: feature extraction and the honest train/eval loop.

These do not touch Postgres/Redis at all -- pure in-process, deterministic (fixed seeds).
"""
from datetime import datetime, timezone

from app.ml.features import CATEGORIES, FEATURE_COLUMNS, build_feature_frame
from app.ml.generator import simulate_backlog
from app.ml.train import train_and_evaluate


def test_build_feature_frame_shape_and_columns():
    rows = [
        {
            "priority": "urgent",
            "category": "work",
            "estimated_minutes": 30,
            "due_date": datetime(2026, 1, 5, tzinfo=timezone.utc),
            "decision_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    ]
    df = build_feature_frame(rows)
    assert list(df.columns) == FEATURE_COLUMNS
    assert df.iloc[0]["priority_num"] == 4
    assert df.iloc[0]["category_work"] == 1.0
    assert df.iloc[0]["is_overdue"] == 0.0


def test_build_feature_frame_overdue_flag():
    rows = [
        {
            "priority": "low",
            "category": "general",
            "estimated_minutes": 15,
            "due_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "decision_time": datetime(2026, 1, 5, tzinfo=timezone.utc),
        }
    ]
    df = build_feature_frame(rows)
    assert df.iloc[0]["is_overdue"] == 1.0
    assert df.iloc[0]["days_until_due"] < 0


def test_build_feature_frame_no_due_date_defaults():
    rows = [{"priority": "medium", "category": "general", "estimated_minutes": 20, "due_date": None}]
    df = build_feature_frame(rows, decision_time=datetime.now(timezone.utc))
    assert df.iloc[0]["has_due_date"] == 0.0
    assert df.iloc[0]["days_until_due"] == 30.0


def test_simulate_backlog_produces_full_completion_order():
    tasks = simulate_backlog(n_tasks=80, seed=3)
    assert len(tasks) == 80
    ranks = sorted(t.completion_rank for t in tasks)
    assert ranks == list(range(1, 81))
    # every task actually got a completion time strictly after its creation time
    assert all(t.completed_at >= t.created_at for t in tasks)


def test_simulate_backlog_is_deterministic_given_seed():
    a = simulate_backlog(n_tasks=50, seed=99)
    b = simulate_backlog(n_tasks=50, seed=99)
    assert [t.completion_rank for t in a] == [t.completion_rank for t in b]
    assert [t.true_urgency for t in a] == [t.true_urgency for t in b]


def test_train_and_evaluate_reports_real_bounded_metrics(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.get_settings(), "model_artifact_dir", str(tmp_path))
    metrics = train_and_evaluate(n_tasks=300, seed=11)

    # honest sanity bounds, not a fabricated exact number: NDCG in (0, 1], tau in [-1, 1],
    # and meaningfully better than random (tau near 0 would mean the model learned nothing)
    assert 0.0 < metrics["ndcg_at_10"] <= 1.0
    assert -1.0 <= metrics["kendall_tau"] <= 1.0
    assert metrics["kendall_tau"] > 0.05
    assert metrics["n_train"] + metrics["n_test"] == 300
    assert (tmp_path / "ranker.joblib").exists()
    assert (tmp_path / "metrics.json").exists()


def test_feature_importances_sum_reasonably():
    metrics = train_and_evaluate(n_tasks=150, seed=5)
    total = sum(metrics["feature_importances"].values())
    assert 0.9 <= total <= 1.1
    assert set(metrics["feature_importances"].keys()) == set(FEATURE_COLUMNS)
    assert len(CATEGORIES) == 6
