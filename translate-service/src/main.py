"""Entry point — uvicorn main:app (PYTHONPATH=src).

Chạy đúng 1 worker (uvicorn mặc định): thread dịch, generation token chống
2 run cùng 1 job và giãn cách gọi AI đều nằm trong bộ nhớ process.
"""
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_.auth import token_auth_middleware, warn_if_unprotected
from platform_.config import config
from platform_.db import SessionLocal, init_db
from platform_.settings_store import get_all, seed_defaults
from translate.api.routers import router as translate_router
from translate.application.callback import notify_crawl
from translate.domain.entities import AiProvider, JobStatus, VariantStatus
from translate.infrastructure.persistence.models import JobModel, VariantModel, WorkModel
from translate.infrastructure.persistence.repositories import AiProviderRepository

INTERRUPTED_BY_RESTART = "Bị gián đoạn do service khởi động lại (interrupted by restart) — bấm Resume để chạy tiếp"
log = logging.getLogger(__name__)


def _push_providers_to_ai() -> None:
    from translate.infrastructure.ai_registry import export_local_providers

    for _ in range(8):
        try:
            export_local_providers()
            return
        except Exception:  # noqa: BLE001 — ai-service có thể chưa lên
            log.warning("Chưa đẩy nhà AI sang ai-service, thử lại")
            time.sleep(2)


def _reset_interrupted_jobs(db) -> list[tuple[str | None, str | None]]:
    """Thread dịch sống trong process — restart là chết hết, nhưng DB vẫn ghi
    RUNNING/QUEUED nên job kẹt mãi (Resume từ chối job RUNNING). Đưa về
    CANCELLED (giống Cancel tay) để Resume chạy tiếp được các segment còn lại.

    Trả (callback_url, external_id) của các Work bị ảnh hưởng để báo crawl."""
    active = [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
    variant_ids = [
        vid for (vid,) in db.query(JobModel.variant_id).filter(JobModel.status.in_(active)).all()
    ]
    if not variant_ids:
        return []
    targets = (
        db.query(WorkModel.callback_url, WorkModel.external_id)
        .join(VariantModel, VariantModel.work_id == WorkModel.id)
        .filter(VariantModel.id.in_(variant_ids))
        .distinct()
        .all()
    )
    db.query(JobModel).filter(JobModel.status.in_(active)).update(
        {JobModel.status: JobStatus.CANCELLED.value, JobModel.error: INTERRUPTED_BY_RESTART},
        synchronize_session=False,
    )
    db.query(VariantModel).filter(
        VariantModel.id.in_(variant_ids),
        VariantModel.status.in_([VariantStatus.QUEUED.value, VariantStatus.RUNNING.value]),
    ).update({VariantModel.status: VariantStatus.PENDING.value}, synchronize_session=False)
    db.commit()
    return [(cb, ext) for cb, ext in targets]


def _notify_interrupted(targets: list[tuple[str | None, str | None]]) -> None:
    for callback_url, external_id in targets:
        notify_crawl(
            callback_url=callback_url,
            external_id=external_id,
            status="cancelled",
            message=INTERRUPTED_BY_RESTART,
        )


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
        targets = _reset_interrupted_jobs(db)
    finally:
        db.close()
    if targets:
        # Gọi mạng nền — crawl-service chưa lên thì không chặn startup.
        threading.Thread(target=_notify_interrupted, args=(targets,), daemon=True).start()
    if config.ai_api_base_url:
        threading.Thread(target=_push_providers_to_ai, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    warn_if_unprotected()
    _seed_startup_data()
    yield


app = FastAPI(title="Translate Service API", lifespan=lifespan)

# Auth thêm TRƯỚC CORS → CORS bọc ngoài, response 401 vẫn có header CORS.
app.middleware("http")(token_auth_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Folio-Token", "Authorization"],
)

app.include_router(translate_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
