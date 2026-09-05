from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_current_user
from app.core.ws_manager import manager
from app.models.models import Interaction, Task, User
from app.schemas import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _bump_and_notify(db: Session, user: User) -> int:
    user.sync_version += 1
    db.add(user)
    return user.sync_version


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Task]:
    q = db.query(Task).filter(Task.user_id == user.id, Task.is_deleted.is_(False))
    if status_filter:
        q = q.filter(Task.status == status_filter)
    return q.order_by(Task.created_at.desc()).all()


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Task:
    version = _bump_and_notify(db, user)
    task = Task(user_id=user.id, sync_version=version, **body.model_dump())
    db.add(task)
    db.flush()  # populate task.id (a Python-side default applied at flush, not at __init__)
    db.add(Interaction(user_id=user.id, task_id=task.id, event_type="created"))
    db.commit()
    db.refresh(task)
    await manager.send_to_user(user.id, {"type": "task_created", "task_id": task.id})
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id or task.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str, body: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id or task.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    was_completed = task.status == "completed"
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    if task.status == "completed" and not was_completed:
        task.completed_at = datetime.now(timezone.utc)
        db.add(Interaction(user_id=user.id, task_id=task.id, event_type="completed"))
    elif task.status == "in_progress" and was_completed is False and body.status == "in_progress":
        db.add(Interaction(user_id=user.id, task_id=task.id, event_type="started"))

    task.sync_version = _bump_and_notify(db, user)
    db.commit()
    db.refresh(task)
    await manager.send_to_user(user.id, {"type": "task_updated", "task_id": task.id})
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.is_deleted = True
    task.sync_version = _bump_and_notify(db, user)
    db.commit()
    await manager.send_to_user(user.id, {"type": "task_deleted", "task_id": task.id})
