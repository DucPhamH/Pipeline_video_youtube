"""Entry point — uvicorn main:app (PYTHONPATH=src)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_.config import config
from platform_.db import SessionLocal, init_db
from platform_.settings_store import get_all, seed_defaults
from translate.api.routers import router as translate_router
from translate.domain.entities import AiProvider
from translate.infrastructure.persistence.repositories import AiProviderRepository


def _seed_ai_providers(db) -> None:
    """Đảm bảo registry AI luôn có ít nhất Mock; migrate 1 lần config cũ (nếu có)."""
    repo = AiProviderRepository(db)
    existing = repo.list_all()
    if not any(p.kind == "mock" for p in existing):
        repo.add(
            AiProvider(
                id=None,
                label="Mock (dev)",
                kind="mock",
                provider="mock",
                base_url="",
                model="mock",
                api_key="",
                requires_api_key=False,
                sort_order=0,
            )
        )
    # Migrate config global cũ 1 lần — chỉ khi chưa có provider "thật" nào khác Mock.
    if not any(p.kind != "mock" for p in existing):
        values = get_all(db)
        old_provider = str(values.get("translate.provider") or "mock")
        old_key = str(values.get("translate.openai_api_key") or "")
        if old_provider != "mock" and old_key.strip():
            repo.add(
                AiProvider(
                    id=None,
                    label="Cài đặt cũ",
                    kind="custom",
                    provider="openai",
                    base_url=str(values.get("translate.openai_base_url") or ""),
                    model=str(values.get("translate.openai_model") or "deepseek-chat"),
                    api_key=old_key,
                    requires_api_key=True,
                    sort_order=repo.count(),
                )
            )
    db.commit()


def _seed_startup_data() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_defaults(db)
        _seed_ai_providers(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_startup_data()
    yield


app = FastAPI(title="Translate Service API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(translate_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
