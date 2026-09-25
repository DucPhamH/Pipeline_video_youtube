"""APScheduler — tick mỗi phút; chỉ quét site đã bật lịch hàng ngày
trong setting riêng (daily_enabled + daily_genre_key + giờ). Lỗi 1 site
không dừng site khác."""
from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from crawl.application.use_cases import CrawlGenreUseCase, CrawlNovelUseCase, RawTextStorage
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)
from crawl.infrastructure.sources.browser_fetch import close_browser
from crawl.infrastructure.sources.registry import SOURCES, get_source
from platform_.config import config
from platform_.db import SessionLocal
from platform_.locks import AlreadyRunningError, keyed_lock
from platform_.settings_store import get_all, get_per_site_int, get_per_site_setting, get_setting
from platform_.terminal_ui import report_progress

logger = logging.getLogger("scheduler")

# Tránh chạy 2 lần cùng site trong cùng 1 ngày (tick mỗi phút khớp giờ:phút).
_fired_dates: set[tuple[str, str]] = set()


def sites_due_now(
    *,
    now: dt.datetime,
    source_keys: list[str],
    get_enabled,
    get_hour,
    get_minute,
    get_genre_key,
    already_fired: set[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Thuần — trả [(source_key, genre_key), ...] cần chạy lúc `now`.

    Dùng cho cả tick thật và unit test. `already_fired` chứa (source_key, YYYY-MM-DD).
    """
    day = now.date().isoformat()
    fired = already_fired if already_fired is not None else set()
    due: list[tuple[str, str]] = []
    for source_key in source_keys:
        if not get_enabled(source_key):
            continue
        try:
            hour = int(get_hour(source_key))
            minute = int(get_minute(source_key))
        except (TypeError, ValueError):
            continue
        if now.hour != hour or now.minute != minute:
            continue
        genre_key = (get_genre_key(source_key) or "").strip()
        if not genre_key:
            continue
        stamp = (source_key, day)
        if stamp in fired:
            continue
        due.append((source_key, genre_key))
    return due


def _prune_fired(today: str) -> None:
    stale = {item for item in _fired_dates if item[1] != today}
    _fired_dates.difference_update(stale)


def run_daily_crawl_tick() -> None:
    """Tick mỗi phút — chỉ chạy site đã cấu hình lịch hàng ngày."""
    now = dt.datetime.now()
    today = now.date().isoformat()
    _prune_fired(today)

    db = SessionLocal()
    try:
        due = sites_due_now(
            now=now,
            source_keys=list(SOURCES.keys()),
            get_enabled=lambda sk: bool(get_per_site_setting(db, "daily_enabled", sk)),
            get_hour=lambda sk: get_per_site_setting(db, "daily_hour", sk),
            get_minute=lambda sk: get_per_site_setting(db, "daily_minute", sk),
            get_genre_key=lambda sk: get_per_site_setting(db, "daily_genre_key", sk),
            already_fired=_fired_dates,
        )
        if not due:
            return

        genre_repo = SqlAlchemyGenreRepository(db)
        crawl_novel_use_case = CrawlNovelUseCase(
            novel_repo=SqlAlchemyNovelRepository(db),
            chapter_repo=SqlAlchemyChapterRepository(db),
            storage=RawTextStorage(config.raw_dir),
            source_resolver=get_source,
            on_progress=report_progress,
        )
        use_case = CrawlGenreUseCase(
            novel_repo=SqlAlchemyNovelRepository(db),
            genre_repo=genre_repo,
            crawl_novel_use_case=crawl_novel_use_case,
            source_resolver=get_source,
            get_scan_window=lambda source_key: get_per_site_int(db, "scan_window", source_key),
            get_max_chapters_per_story=lambda source_key: get_per_site_int(
                db, "max_chapters_per_story", source_key
            ),
            get_narration_filter=lambda source_key: get_per_site_setting(db, "narration_filter", source_key),
            get_max_pages_per_scan=lambda source_key: get_per_site_int(db, "max_pages_per_scan", source_key),
            get_max_consecutive_errors=lambda source_key: get_per_site_int(
                db, "max_consecutive_errors", source_key
            ),
            get_completion_filter=lambda source_key: get_per_site_setting(
                db, "completion_filter", source_key
            ),
            on_progress=report_progress,
        )

        summaries: list[dict] = []
        for source_key, genre_key in due:
            _fired_dates.add((source_key, today))
            genre = next(
                (g for g in genre_repo.list_by_source_key(source_key) if g.genre_key == genre_key),
                None,
            )
            if genre is None or genre.id is None:
                logger.warning(
                    "Site %s lịch hàng ngày trỏ genre_key=%r nhưng không tìm thấy — bỏ qua",
                    source_key,
                    genre_key,
                )
                continue
            try:
                with keyed_lock(f"genre-run:{genre.id}"):
                    result = use_case.execute(genre.id)
                logger.info("Daily crawl %s / %s: %s", source_key, genre.label, result)
                summaries.append(
                    {
                        "source_key": source_key,
                        "genre_label": genre.label,
                        "discovered": result.discovered,
                        "synced": result.synced,
                        "rejected": result.rejected,
                        "errors": result.errors,
                    }
                )
            except AlreadyRunningError:
                logger.info(
                    "Bỏ qua daily %s / %s — đang có yêu cầu khác xử lý",
                    source_key,
                    genre.label,
                )
            except Exception:
                logger.exception("Lỗi không mong đợi khi daily crawl %s / %s", source_key, genre.label)
                summaries.append(
                    {
                        "source_key": source_key,
                        "genre_label": genre.label if genre else genre_key,
                        "discovered": 0,
                        "synced": 0,
                        "rejected": 0,
                        "errors": 1,
                    }
                )

        webhook = (get_setting(db, "notify.webhook_url", "") or "").strip()
        if webhook and summaries:
            from crawl.application.notify import format_scan_summary, send_webhook

            send_webhook(
                webhook,
                title="Crawl daily xong",
                body=format_scan_summary(summaries),
            )
    finally:
        close_browser()
        db.close()


# Alias cũ — test/docs có thể còn gọi tên này.
run_daily_crawl_job = run_daily_crawl_tick


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    if config.crawl_enabled:
        # Tick mỗi phút; logic due nằm trong sites_due_now (per-site hour/minute).
        scheduler.add_job(
            run_daily_crawl_tick,
            trigger="interval",
            minutes=1,
            id="daily_crawl_tick",
            # Chạy ngay sau start để không đợi đủ 1 phút nếu vừa khớp giờ.
            next_run_time=dt.datetime.now(),
        )
    return scheduler
