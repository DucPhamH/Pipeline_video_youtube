"""Entry point web server — chạy: uvicorn main:app --reload (từ backend/src)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.orm import Session

from crawl.api.routers import router as crawl_router
from crawl.domain.entities import GenreRunStatus, NovelLifecycle
from crawl.infrastructure.sources.registry import GENRE_SEEDS, SOURCES, catalog_genre_keys
from crawl.infrastructure.persistence.repositories import SqlAlchemyGenreRepository, SqlAlchemyNovelRepository
from platform_.auth import token_auth_middleware, warn_if_open
from platform_.config import config
from platform_.db import SessionLocal, init_db
from platform_.settings_store import PER_SITE_CRAWL_DEFAULTS, per_site_key, seed_defaults, seed_missing

_NON_ZH_FILTERS_MIGRATION_KEY = "crawl.migration.non_zh_filters_v1"


def _source_content_locale(source_key: str) -> str:
    source = SOURCES.get(source_key)
    cfg = getattr(source, "cfg", None) if source is not None else None
    return getattr(cfg, "content_locale", "zh") if cfg else "zh"


def _seed_per_site_settings(db: Session) -> None:
    """Mỗi site có setting quét RIÊNG (scan_window, ngưỡng ngắn, lọc ngôi
    kể...) thay vì dùng chung 1 giá trị toàn hệ thống (mục 9.0, sửa
    16/9/2026) — nhân bản `PER_SITE_CRAWL_DEFAULTS` thành 1 dòng/site."""
    from platform_.settings_store import SettingsModel, get_setting

    per_site_defaults: dict[str, object] = {}
    for source_key in SOURCES:
        defaults = dict(PER_SITE_CRAWL_DEFAULTS)
        # Theo ngôn ngữ nội dung, không theo tab region (TW zh vẫn completed_only).
        if _source_content_locale(source_key) != "zh":
            defaults["narration_filter"] = "any"
            defaults["completion_filter"] = "any"
        for key, default in defaults.items():
            per_site_defaults[per_site_key(key, source_key)] = default
    seed_missing(db, per_site_defaults)

    # One-shot: site non-zh từng bị seed nhầm default ZH. Không chạy lại mỗi
    # boot — tránh ghi đè lựa chọn user sau này.
    if get_setting(db, _NON_ZH_FILTERS_MIGRATION_KEY) is None:
        for source_key in SOURCES:
            if _source_content_locale(source_key) == "zh":
                continue
            for setting_key, stale_value, new_value in (
                ("completion_filter", "completed_only", "any"),
                ("narration_filter", "first_person", "any"),
            ):
                key = per_site_key(setting_key, source_key)
                if get_setting(db, key) != stale_value:
                    continue
                row = db.get(SettingsModel, key)
                if row is None:
                    continue
                row.value = new_value
        db.add(SettingsModel(key=_NON_ZH_FILTERS_MIGRATION_KEY, value=True))
        db.commit()


def _recover_interrupted_genre_runs(genre_repo: SqlAlchemyGenreRepository) -> None:
    """Nếu server bị restart/crash giữa lúc 1 genre đang "running", thread
    nền của tiến trình CŨ đã chết theo — không còn ai cập nhật nốt
    `last_run_status`, genre đó kẹt "running" MÃI MÃI dù thực tế chẳng có gì
    đang chạy (lock in-process cũng mất theo tiến trình cũ, chỉ riêng DB
    status là còn sót lại). Hậu quả: nút "Quét ngay" ở FE bị disable vĩnh
    viễn (dựa vào đúng field này), không cách nào tự bấm lại được qua UI —
    bug thật đã gặp (16/9/2026). Reset về "error" ngay lúc khởi động."""
    for genre in genre_repo.list_all():
        if genre.last_run_status == GenreRunStatus.RUNNING:
            genre.mark_run_finished(
                status=GenreRunStatus.ERROR, discovered=0, rejected=0, errors=1,
                messages=["Bị gián đoạn do server khởi động lại giữa lúc đang quét — thử lại sau"],
            )
            genre_repo.update_run_state(genre)


def _recover_interrupted_novel_crawls(novel_repo: SqlAlchemyNovelRepository) -> None:
    """Y hệt bug/fix của `_recover_interrupted_genre_runs()` ở trên nhưng
    cho TỪNG TRUYỆN: server crash/restart giữa lúc 1 novel đang
    `lifecycle_status="crawling"` (thread nền + khoá `crawl-novel:{id}`
    chết theo tiến trình cũ) khiến novel đó kẹt "crawling" MÃI MÃI — hậu
    quả nặng hơn cấp genre vì "Thử lại" (`POST /novels/{id}/retry`) CHỈ
    nhận truyện đang `error`/`fully_crawled` (routers.py), "crawling" không
    nằm trong 2 trạng thái đó nên không có cách nào tự bấm lại được qua UI.
    Bug thật đã báo (17/9/2026, cùng dạng với genre). Reset về "error" ngay
    lúc khởi động — resume vẫn đúng vì `last_chapter_index`/Chapter đã lưu
    không mất, "Thử lại" sẽ tiếp tục đúng từ chỗ dở dang."""
    for novel in novel_repo.list_all(status=NovelLifecycle.CRAWLING.value, limit=None):
        novel.mark_error("Bị gián đoạn do server khởi động lại giữa lúc đang crawl — bấm Thử lại")
        novel_repo.update(novel)


def _seed_startup_data() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_defaults(db)
        _seed_per_site_settings(db)
        genre_repo = SqlAlchemyGenreRepository(db)
        for seed in GENRE_SEEDS:
            genre_repo.get_or_create(**seed)
        # Option cũ không còn trong catalog (vd *_hot) — tắt enabled để
        # job lịch không quét; select FE lọc theo catalog_genre_keys().
        allowed = catalog_genre_keys()
        for genre in genre_repo.list_all():
            if (genre.source_key, genre.genre_key) not in allowed and genre.enabled:
                genre.enabled = False
                genre_repo.update(genre)
        _recover_interrupted_genre_runs(genre_repo)
        _recover_interrupted_novel_crawls(SqlAlchemyNovelRepository(db))
        # Deploy đầu: site đã bật lịch mà giờ hẹn hôm nay đã qua -> không quét ngay.
        from platform_.scheduler import seed_last_fired_on_startup

        seed_last_fired_on_startup(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    warn_if_open()
    _seed_startup_data()
    from platform_.scheduler import create_scheduler

    scheduler = create_scheduler()
    if scheduler.get_jobs():
        scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Crawl Service API", lifespan=lifespan)

# Thứ tự: auth thêm TRƯỚC để CORS bọc ngoài cùng — response 401 vẫn có header
# CORS, preflight OPTIONS không bị đòi token.
app.add_middleware(BaseHTTPMiddleware, dispatch=token_auth_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    # "*" + allow_credentials: Starlette phản hồi đúng header được xin
    # (gồm X-Folio-Token, Authorization).
    allow_headers=["*", "X-Folio-Token", "Authorization"],
)

app.include_router(crawl_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
