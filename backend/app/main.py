import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.ml.seed import seed_demo_user
from app.ml.train import train_and_evaluate
from app.routers import auth, recommendations, sync, tasks, ws

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger("tasks")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    if settings.seed_synthetic_data:
        db = SessionLocal()
        try:
            seed_demo_user(db)
        finally:
            db.close()
    artifact_path = Path(settings.model_artifact_dir) / "ranker.joblib"
    if not artifact_path.exists():
        logger.info("No trained ranker found; training one now from the synthetic generator")
        try:
            metrics = train_and_evaluate()
            logger.info("Trained ranker: %s", metrics)
        except Exception:
            logger.exception("Ranker training failed at startup; falling back to heuristic scoring")
    yield


app = FastAPI(
    title="Offline-First Task Management Platform",
    description="PWA offline-first task manager with sync engine, JWT auth, and an ML "
    "task-prioritization ranker.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(sync.router)
app.include_router(recommendations.router)
app.include_router(ws.router)

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed; /metrics disabled")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
