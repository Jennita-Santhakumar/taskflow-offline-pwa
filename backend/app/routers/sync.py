from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_current_user
from app.core.ws_manager import manager
from app.models.models import SyncCursor, Task, User
from app.schemas import (
    SyncPullResponse,
    SyncPushItem,
    SyncPushRequest,
    SyncPushResponse,
    SyncPushResult,
    TaskOut,
)

router = APIRouter(prefix="/sync", tags=["sync"])

PULL_PAGE_SIZE = 200


def _apply_upsert(db: Session, user: User, item: SyncPushItem) -> SyncPushResult:
    fields = {
        k: v
        for k, v in item.model_dump(exclude={"client_id", "op", "id", "updated_at"}).items()
        if v is not None
    }

    existing: Task | None = db.get(Task, item.id) if item.id else None
    if existing is not None and existing.user_id == user.id:
        # last-write-wins conflict resolution by updated_at, mirroring the PWA's mergePulledData logic
        existing_updated = existing.updated_at
        if existing_updated.tzinfo is None:
            existing_updated = existing_updated.replace(tzinfo=item.updated_at.tzinfo)
        if item.updated_at >= existing_updated:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.updated_at = item.updated_at
            status_str = "applied"
        else:
            status_str = "conflict_resolved_remote_wins"
        user.sync_version += 1
        existing.sync_version = user.sync_version
        db.add(existing)
        return SyncPushResult(
            client_id=item.client_id, server_id=existing.id, status=status_str, sync_version=existing.sync_version
        )

    # brand-new task from the client (never synced before)
    user.sync_version += 1
    task = Task(
        user_id=user.id,
        sync_version=user.sync_version,
        title=fields.get("title") or "Untitled",
        description=fields.get("description"),
        priority=fields.get("priority") or "medium",
        category=fields.get("category") or "general",
        status=fields.get("status") or "pending",
        due_date=fields.get("due_date"),
        estimated_minutes=fields.get("estimated_minutes"),
        updated_at=item.updated_at,
    )
    db.add(task)
    db.flush()
    return SyncPushResult(client_id=item.client_id, server_id=task.id, status="applied", sync_version=task.sync_version)


def _apply_delete(db: Session, user: User, item: SyncPushItem) -> SyncPushResult | None:
    if not item.id:
        return None
    task = db.get(Task, item.id)
    if task is None or task.user_id != user.id:
        return None
    task.is_deleted = True
    user.sync_version += 1
    task.sync_version = user.sync_version
    db.add(task)
    return SyncPushResult(client_id=item.client_id, server_id=task.id, status="applied", sync_version=task.sync_version)


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    body: SyncPushRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SyncPushResponse:
    results: list[SyncPushResult] = []
    for item in body.items:
        if item.op == "delete":
            result = _apply_delete(db, user, item)
        else:
            result = _apply_upsert(db, user, item)
        if result:
            results.append(result)

    cursor = (
        db.query(SyncCursor)
        .filter(SyncCursor.user_id == user.id, SyncCursor.device_id == body.device_id)
        .first()
    )
    if cursor is None:
        cursor = SyncCursor(user_id=user.id, device_id=body.device_id, last_synced_version=user.sync_version)
        db.add(cursor)
    else:
        cursor.last_synced_version = user.sync_version

    db.commit()
    if results:
        await manager.send_to_user(user.id, {"type": "sync_completed", "applied": len(results)})
    return SyncPushResponse(results=results, sync_version=user.sync_version)


@router.get("/pull", response_model=SyncPullResponse)
def sync_pull(
    device_id: str,
    since: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SyncPullResponse:
    query = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.sync_version > since)
        .order_by(Task.sync_version.asc())
    )
    page = query.limit(PULL_PAGE_SIZE + 1).all()
    has_more = len(page) > PULL_PAGE_SIZE
    page = page[:PULL_PAGE_SIZE]

    cursor = (
        db.query(SyncCursor).filter(SyncCursor.user_id == user.id, SyncCursor.device_id == device_id).first()
    )
    new_cursor_value = page[-1].sync_version if page else since
    if cursor is None:
        cursor = SyncCursor(user_id=user.id, device_id=device_id, last_synced_version=new_cursor_value)
        db.add(cursor)
    else:
        cursor.last_synced_version = max(cursor.last_synced_version, new_cursor_value)
    db.commit()

    return SyncPullResponse(
        tasks=[TaskOut.model_validate(t) for t in page],
        sync_version=new_cursor_value,
        has_more=has_more,
    )
