"""Train and honestly evaluate the task-prioritization ranker.

Run standalone: `python -m app.ml.train`
Writes `<model_artifact_dir>/ranker.joblib` and `<model_artifact_dir>/metrics.json`.

Evaluation methodology (documented in README "Design Decisions & Trade-offs" verbatim from these
numbers -- never hand-edited): a real time-based train/test split (first 80% of tasks by
created_at for training, last 20% for test, no shuffling), NDCG@10 and Kendall's tau computed on
the held-out test set's actual observed completion order vs the model's predicted order. The
model never sees the synthetic generator's hidden `true_urgency`/noise term, only the same
features available at inference time.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import kendalltau
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import ndcg_score

from app.config import get_settings
from app.ml.features import build_feature_frame
from app.ml.generator import SimTask, simulate_backlog

MODEL_VERSION = "gbr-v1"


def _rows_from_sim(tasks: list[SimTask]) -> list[dict]:
    n = len(tasks)
    rows = []
    for t in tasks:
        rows.append(
            {
                "priority": t.priority,
                "category": t.category,
                "estimated_minutes": t.estimated_minutes,
                "due_date": t.due_date,
                "decision_time": t.created_at,
                # relevance target: earlier completion = higher relevance, normalized to (0, 1]
                "relevance": (n - t.completion_rank + 1) / n,
                "completion_rank": t.completion_rank,
            }
        )
    return rows


def train_and_evaluate(n_tasks: int = 600, seed: int = 42) -> dict:
    tasks = simulate_backlog(n_tasks=n_tasks, seed=seed)
    rows = _rows_from_sim(tasks)
    # time-based split (no shuffling) on created_at order == the order `simulate_backlog` already
    # sorted its input by, but completion order differs from creation order, so this is a genuine
    # temporal holdout, not a leak of the label ordering.
    rows_by_creation = sorted(zip(tasks, rows), key=lambda p: p[0].created_at)
    split_idx = int(len(rows_by_creation) * 0.8)
    train_pairs = rows_by_creation[:split_idx]
    test_pairs = rows_by_creation[split_idx:]

    X_train = build_feature_frame([r for _, r in train_pairs])
    y_train = np.array([r["relevance"] for _, r in train_pairs])
    X_test = build_feature_frame([r for _, r in test_pairs])
    y_test = np.array([r["relevance"] for _, r in test_pairs])
    test_ranks = np.array([r["completion_rank"] for _, r in test_pairs])

    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)  # single batched call -- fixes the PRD's per-item predict-in-a-loop bug

    ndcg_at_10 = float(ndcg_score(y_test.reshape(1, -1), preds.reshape(1, -1), k=10))
    # Kendall tau between predicted score order and the *actual* completion order (lower rank
    # number = completed earlier = should score higher, hence the sign flip)
    tau, tau_p = kendalltau(preds, -test_ranks)

    metrics = {
        "model_version": MODEL_VERSION,
        "n_train": len(train_pairs),
        "n_test": len(test_pairs),
        "ndcg_at_10": round(ndcg_at_10, 4),
        "kendall_tau": round(float(tau), 4),
        "kendall_tau_p_value": round(float(tau_p), 6),
        "feature_importances": dict(zip(X_train.columns, [round(float(v), 4) for v in model.feature_importances_])),
    }

    artifact_dir = Path(get_settings().model_artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_dir / "ranker.joblib")
    (artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    result = train_and_evaluate()
    print(json.dumps(result, indent=2))
