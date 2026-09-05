"""Synthetic-but-honest task/completion-order generator.

Simulates one user's backlog over time: tasks arrive with realistic
priority/category/due-date/duration attributes, and a *hidden* ground-truth "true urgency" score
(a deterministic weighted formula plus genuine Gaussian noise) drives a greedy sequential
work-through-the-backlog policy. The observed completion order is the label signal the ranker
learns from -- the model never sees `true_urgency` directly, only the same features a real
/recommendations request would have, so the reported evaluation numbers are a real measurement of
how well the model recovers an unseen, noisy preference signal from features alone (not a
memorized number).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.ml.features import CATEGORIES, PRIORITY_WEIGHT

CATEGORY_PREFERENCE = {  # a synthetic user's mild category bias, part of the hidden signal
    "work": 1.2,
    "health": 0.8,
    "learning": 0.3,
    "personal": 0.0,
    "errands": -0.4,
    "general": -0.2,
}


@dataclass
class SimTask:
    task_id: str
    created_at: datetime
    priority: str
    category: str
    due_date: datetime | None
    estimated_minutes: int
    true_urgency: float
    completed_at: datetime | None = None
    completion_rank: int | None = None


def _random_task(idx: int, rng: random.Random, base_time: datetime) -> SimTask:
    # A 30-day arrival window against ~70min average task duration lets a genuine backlog build
    # up (so the greedy urgency-first policy actually has candidates to choose between) without
    # making the ordering trivially easy to recover -- a much wider window (e.g. 90 days) spaces
    # arrivals out enough that the backlog rarely exceeds 1-2 open tasks, so completion order
    # degenerates to ~FIFO-by-arrival and the "true_urgency" signal barely shows up in the
    # observed label at all (measured Kendall tau ~0 against the wider window, verified by hand).
    created_at = base_time + timedelta(minutes=rng.uniform(0, 30 * 24 * 60))
    priority = rng.choices(list(PRIORITY_WEIGHT), weights=[3, 4, 2, 1])[0]
    category = rng.choice(CATEGORIES)
    has_due = rng.random() < 0.7
    due_date = created_at + timedelta(days=rng.uniform(0.5, 21)) if has_due else None
    estimated_minutes = int(rng.choice([15, 30, 45, 60, 90, 120, 180]))

    days_until_due = (due_date - created_at).total_seconds() / 86400.0 if due_date else 30.0
    due_urgency = max(0.0, 14.0 - days_until_due) / 14.0
    noise = rng.gauss(0, 1.6)
    true_urgency = (
        2.2 * PRIORITY_WEIGHT[priority]
        + 3.0 * due_urgency
        - estimated_minutes / 240.0
        + CATEGORY_PREFERENCE[category]
        + noise
    )
    return SimTask(
        task_id=f"sim-{idx}",
        created_at=created_at,
        priority=priority,
        category=category,
        due_date=due_date,
        estimated_minutes=estimated_minutes,
        true_urgency=true_urgency,
    )


def simulate_backlog(n_tasks: int = 500, seed: int = 42) -> list[SimTask]:
    """Discrete-event simulation: a user works through whichever open task currently has the
    highest true_urgency, one at a time, advancing a simulated clock by that task's duration plus
    a small idle gap. Returns tasks annotated with completed_at/completion_rank."""
    rng = random.Random(seed)
    base_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
    tasks = [_random_task(i, rng, base_time) for i in range(n_tasks)]
    tasks.sort(key=lambda t: t.created_at)

    pending = list(tasks)
    completed: list[SimTask] = []
    sim_clock = tasks[0].created_at

    while pending:
        available = [t for t in pending if t.created_at <= sim_clock]
        if not available:
            sim_clock = min(t.created_at for t in pending)
            continue
        chosen = max(available, key=lambda t: t.true_urgency)
        chosen.completed_at = sim_clock
        chosen.completion_rank = len(completed) + 1
        completed.append(chosen)
        pending.remove(chosen)
        idle_gap = rng.uniform(0, 45)
        sim_clock = sim_clock + timedelta(minutes=chosen.estimated_minutes + idle_gap)

    return completed
