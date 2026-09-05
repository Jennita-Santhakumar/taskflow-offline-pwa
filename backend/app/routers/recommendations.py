from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db import get_db
from app.core.redis_client import get_redis
from app.core.security import get_current_user
from app.ml.features import build_feature_frame
from app.ml.train import MODEL_VERSION
from app.models.models import Task, User
from app.schemas import RecommendationItem, RecommendationsResponse

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
logger = logging.getLogger("tasks.recommendations")

_model = None
_model_load_attempted = False


def _load_model():
    """Fail-once: a missing/untrained model degrades to a deterministic fallback instead of
    re-attempting a joblib.load() on every request."""
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model
    _model_load_attempted = True
    path = Path(get_settings().model_artifact_dir) / "ranker.joblib"
    if path.exists():
        _model = joblib.load(path)
        logger.info("Loaded ranker model from %s", path)
    else:
        logger.warning("No trained model found at %s; falling back to a heuristic score", path)
    return _model


def _heuristic_score(rows: list[dict]) -> list[float]:
    from app.ml.features import PRIORITY_WEIGHT

    scores = []
    for r in rows:
        s = PRIORITY_WEIGHT.get(r["priority"], 2) * 2.0
        if r.get("due_date"):
            days = (r["due_date"] - r["decision_time"]).total_seconds() / 86400.0
            s += max(0.0, 14.0 - days) / 14.0 * 3.0
        scores.append(s)
    return scores


@router.get("/next-tasks", response_model=RecommendationsResponse)
def next_tasks(
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    cache_key = f"recs:{user.id}:{user.sync_version}:{limit}"
    r = get_redis()
    cached = r.get(cache_key)
    if cached:
        payload = json.loads(cached)
        payload["cached"] = True
        return RecommendationsResponse(**payload)

    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.is_deleted.is_(False), Task.status.in_(["pending", "in_progress"]))
        .all()
    )

    if not open_tasks:
        response = RecommendationsResponse(
            items=[], model_version=MODEL_VERSION, generated_at=datetime.now(timezone.utc), cached=False
        )
        r.setex(cache_key, get_settings().recommendation_cache_ttl_seconds, response.model_dump_json())
        return response

    now = datetime.now(timezone.utc)
    rows = [
        {
            "priority": t.priority,
            "category": t.category,
            "estimated_minutes": t.estimated_minutes,
            "due_date": t.due_date,
            "decision_time": now,
        }
        for t in open_tasks
    ]

    model = _load_model()
    if model is not None:
        features = build_feature_frame(rows, decision_time=now)
        scores = model.predict(features)  # one batched call, not a per-item loop (the PRD's bug)
    else:
        scores = _heuristic_score(rows)

    ranked = sorted(zip(open_tasks, scores), key=lambda p: p[1], reverse=True)[:limit]
    items = [
        RecommendationItem(
            task_id=t.id,
            title=t.title,
            score=round(float(score), 4),
            rank=i + 1,
            reason=_reason(t, now),
        )
        for i, (t, score) in enumerate(ranked)
    ]
    response = RecommendationsResponse(
        items=items, model_version=MODEL_VERSION if model is not None else "heuristic-fallback",
        generated_at=now, cached=False,
    )
    r.setex(cache_key, get_settings().recommendation_cache_ttl_seconds, response.model_dump_json())
    return response


def _reason(task: Task, now: datetime) -> str:
    parts = []
    if task.priority in ("high", "urgent"):
        parts.append(f"{task.priority} priority")
    if task.due_date:
        days = (task.due_date - now).total_seconds() / 86400.0
        if days < 0:
            parts.append("overdue")
        elif days < 2:
            parts.append("due soon")
    if not parts:
        parts.append("open task")
    return ", ".join(parts)
