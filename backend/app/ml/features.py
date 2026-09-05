"""Feature extraction for the task-prioritization ranker.

Shared by training (app/ml/train.py) and inference (app/routers/recommendations.py) so the two
paths can never drift out of sync on column order/encoding.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

PRIORITY_WEIGHT = {"low": 1, "medium": 2, "high": 3, "urgent": 4}
CATEGORIES = ["general", "work", "personal", "health", "learning", "errands"]

FEATURE_COLUMNS = [
    "priority_num",
    "estimated_minutes",
    "has_due_date",
    "days_until_due",
    "is_overdue",
    "decision_hour",
    "decision_dow",
] + [f"category_{c}" for c in CATEGORIES]


def _days_until_due(due_date, decision_time) -> float:
    if due_date is None or pd.isna(due_date):
        return 30.0
    delta = (due_date - decision_time).total_seconds() / 86400.0
    return float(np.clip(delta, -30.0, 60.0))


def build_feature_frame(rows: list[dict], decision_time: datetime | None = None) -> pd.DataFrame:
    """rows: dicts with keys priority, category, estimated_minutes, due_date, created_at
    (decision_time_col optional per-row 'decision_time' overrides the shared `decision_time`,
    used at training time where each task has its own historical decision point)."""
    records = []
    for row in rows:
        dt = row.get("decision_time") or decision_time or datetime.now(timezone.utc)
        due_date = row.get("due_date")
        priority = row.get("priority", "medium")
        category = row.get("category", "general")
        estimated_minutes = row.get("estimated_minutes") or 30
        rec = {
            "priority_num": PRIORITY_WEIGHT.get(priority, 2),
            "estimated_minutes": float(estimated_minutes),
            "has_due_date": 1.0 if due_date is not None and not pd.isna(due_date) else 0.0,
            "days_until_due": _days_until_due(due_date, dt),
            "decision_hour": dt.hour,
            "decision_dow": dt.weekday(),
        }
        rec["is_overdue"] = 1.0 if rec["days_until_due"] < 0 else 0.0
        for c in CATEGORIES:
            rec[f"category_{c}"] = 1.0 if category == c else 0.0
        records.append(rec)
    return pd.DataFrame.from_records(records, columns=FEATURE_COLUMNS)
