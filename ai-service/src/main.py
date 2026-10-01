"""Entry point — uvicorn main:app (PYTHONPATH=src)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai.api.routers import router as ai_router
from ai.infrastructure.persistence.models import AiProviderModel
from platform_.auth import HEADER, require_token
from platform_.config import config
from platform_.db import SessionLocal, init_db

log = logging.getLogger(__name__)


def _seed_mock() -> None:
    db = SessionLocal()
    try:
        if db.query(AiProviderModel).filter(AiProviderModel.kind == "mock").first():
            return
        db.add(
            AiProviderModel(
                label="Mock (dev)",
                kind="mock",
                provider="mock",
                base_url="",
                model="mock",
                api_key="",
                requires_api_key=0,
                sort_order=0,
            )
        )
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_mock()
    if not config.folio_api_token:
        log.warning("FOLIO_API_TOKEN chưa đặt — API mở cho mọi request")
    yield


app = FastAPI(title="AI Service API", lifespan=lifespan)
app.middleware("http")(require_token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", HEADER],
)
app.include_router(ai_router)


@app.get("/api/health")
@app.get("/api/ai/health")
def health():
    return {"status": "ok"}
