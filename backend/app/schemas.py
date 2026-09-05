from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    category: str = "general"
    due_date: datetime | None = None
    estimated_minutes: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    category: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    estimated_minutes: int | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    priority: str
    category: str
    status: str
    due_date: datetime | None
    estimated_minutes: int | None
    completed_at: datetime | None
    is_deleted: bool
    sync_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncPushItem(BaseModel):
    """One locally-queued mutation, mirroring the PWA's IndexedDB sync_queue row."""

    client_id: str  # local IndexedDB task id, so the server can tell the client which server id it maps to
    op: str  # "upsert" | "delete"
    id: str | None = None  # server task id, if this task has already been synced once
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    category: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    updated_at: datetime  # client's local last-write timestamp, used for last-write-wins conflict resolution


class SyncPushRequest(BaseModel):
    device_id: str
    items: list[SyncPushItem]


class SyncPushResult(BaseModel):
    client_id: str
    server_id: str
    status: str  # "applied" | "conflict_resolved_remote_wins" | "conflict_resolved_local_wins"
    sync_version: int


class SyncPushResponse(BaseModel):
    results: list[SyncPushResult]
    sync_version: int


class SyncPullResponse(BaseModel):
    tasks: list[TaskOut]
    sync_version: int
    has_more: bool


class RecommendationItem(BaseModel):
    task_id: str
    title: str
    score: float
    rank: int
    reason: str


class RecommendationsResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    items: list[RecommendationItem]
    model_version: str
    generated_at: datetime
    cached: bool
