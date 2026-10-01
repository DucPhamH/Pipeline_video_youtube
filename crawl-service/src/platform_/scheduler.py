"""APScheduler — tick mỗi phút; chỉ quét site đã bật lịch hàng ngày
trong setting riêng (daily_enabled + daily_genre_key + giờ). Lỗi 1 site
không dừng site khác."""
from __future__ import annotations

import datetime as dt
import logging
import threading

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
from platform_.locks import AlreadyRunningError, keyed_lock, release, try_acquire
from platform_.settings_store import get_per_site_int, get_per_site_setting, get_setting, set_setting
from platform_.terminal_ui import report_progress

logger = logging.getLogger("scheduler")

# Cache in-process (source_key, YYYY-MM-DD) đã fire — nguồn thật là setting
# `scheduler.daily_last_fired.<source_key>` (sống qua restart).
_fired_dates: set[tuple[str, str]] = set()
_fired_lock = threading.Lock()

LAST_FIRED_KEY_PREFIX = "scheduler.daily_last_fired."


def last_fired_key(source_key: str) -> str:
    return f"{LAST_FIRED_KEY_PREFIX}{source_key}"


def scheduler_now() -> dt.datetime:
    """Giờ "tường" dùng so lịch — `SCHEDULER_TZ` (vd Asia/Ho_Chi_Minh) nếu
    đặt, không thì giờ local của tiến trình (theo biến TZ của OS)."""
    tz_name = (config.scheduler_tz or "").strip()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return dt.datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
        except Exception:
            logger.warning("SCHEDULER_TZ=%r không hợp lệ — dùng giờ local", tz_name)
    return dt.datetime.now()


def sites_due_now(
    *,
    now: dt.datetime,
    source_keys: list[str],
    get_enabled,
    get_hour,
    get_minute,
    get_genre_key,
    already_fired: set[tuple[str, str]] | None = None,
    get_last_fired=None,
) -> list[tuple[str, str]]:
    """Thuần — trả [(source_key, genre_key), ...] cần chạy lúc `now`.

    Site "đến hạn" khi `now` >= giờ hẹn HÔM NAY và hôm nay chưa chạy — không
    đòi khớp đúng giờ:phút (tick trễ vì site trước chạy lâu / server vừa
    bật lại vẫn không lỡ lịch). `already_fired` chứa (source_key,
    YYYY-MM-DD); `get_last_fired(source_key)` trả "YYYY-MM-DD" đã lưu."""
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
        if (now.hour, now.minute) < (hour, minute):
            continue
        genre_key = (get_genre_key(source_key) or "").strip()
        if not genre_key:
            continue
        if (source_key, day) in fired:
            continue
        if get_last_fired is not None and (get_last_fired(source_key) or "") == day:
            continue
        due.append((source_key, genre_key))
    return due


def _schedule_passed_today(db, source_key: str, now: dt.datetime) -> bool:
    try:
        hour = int(get_per_site_setting(db, "daily_hour", source_key))
        minute = int(get_per_site_setting(db, "daily_minute", source_key))
    except (TypeError, ValueError):
        return False
    return (now.hour, now.minute) >= (hour, minute)


def seed_last_fired_if_past(db, source_key: str, *, now: dt.datetime | None = None) -> bool:
    """Lịch vừa bật/sửa mà giờ hẹn hôm nay ĐÃ QUA — ghi last_fired=hôm nay để
    tick kế tiếp không quét ngay lập tức (lần chạy đầu là đúng giờ ngày mai).
    Trả True nếu đã ghi."""
    now = now or scheduler_now()
    if not bool(get_per_site_setting(db, "daily_enabled", source_key)):
        return False
    if not _schedule_passed_today(db, source_key, now):
        return False
    today = now.date().isoformat()
    set_setting(db, last_fired_key(source_key), today)
    with _fired_lock:
        _fired_dates.add((source_key, today))
    return True


def seed_last_fired_on_startup(db, *, now: dt.datetime | None = None) -> list[str]:
    """Lần deploy đầu (chưa có key last_fired nào cho site): site đã bật lịch
    mà giờ hẹn hôm nay đã qua thì coi như hôm nay đã chạy — không quét ngay
    khi vừa khởi động. Site đã có last_fired (ngày cũ) vẫn được bù như cũ."""
    seeded: list[str] = []
    for source_key in SOURCES:
        if get_setting(db, last_fired_key(source_key), None) is not None:
            continue
        if seed_last_fired_if_past(db, source_key, now=now):
            seeded.append(source_key)
    return seeded


def _prune_fired(today: str) -> None:
    stale = {item for item in _fired_dates if item[1] != today}
    _fired_dates.difference_update(stale)


def run_daily_crawl_tick(*, background: bool = True) -> list[threading.Thread]:
    """Tick mỗi phút — chỉ chọn site đến hạn, đánh dấu in-process rồi đẩy
    việc quét sang thread nền (tick trả về ngay, không chặn site khác).
    last_fired trong DB chỉ ghi khi lượt quét THẬT SỰ bắt đầu (đã lấy được
    khoá) — xem `_run_due_sites`."""
    now = scheduler_now()
    today = now.date().isoformat()

    db = SessionLocal()
    try:
        with _fired_lock:
            _prune_fired(today)
            due = sites_due_now(
                now=now,
                source_keys=list(SOURCES.keys()),
                get_enabled=lambda sk: bool(get_per_site_setting(db, "daily_enabled", sk)),
                get_hour=lambda sk: get_per_site_setting(db, "daily_hour", sk),
                get_minute=lambda sk: get_per_site_setting(db, "daily_minute", sk),
                get_genre_key=lambda sk: get_per_site_setting(db, "daily_genre_key", sk),
                already_fired=_fired_dates,
                get_last_fired=lambda sk: get_setting(db, last_fired_key(sk), ""),
            )
            for source_key, _genre_key in due:
                _fired_dates.add((source_key, today))
    finally:
        db.close()

    if not due:
        return []
    if not background:
        _run_due_sites(due, today=today)
        return []
    t = threading.Thread(
        target=_run_due_sites, args=(due,), kwargs={"today": today}, daemon=True, name="daily-crawl"
    )
    t.start()
    return [t]


def _mark_fired(db, source_key: str, today: str) -> None:
    try:
        set_setting(db, last_fired_key(source_key), today)
    except Exception:
        logger.exception("Không lưu được last-fired cho %s", source_key)


def _unmark_fired(source_key: str, today: str) -> None:
    """Không chạy được (đang bị giữ khoá…) — tick sau thử lại."""
    with _fired_lock:
        _fired_dates.discard((source_key, today))


def _run_due_sites(due: list[tuple[str, str]], *, today: str | None = None) -> None:
    """Chạy tuần tự các site đến hạn trong 1 lượt tick (thread nền, session riêng)."""
    today = today or scheduler_now().date().isoformat()
    db = SessionLocal()
    try:
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
                    _mark_fired(db, source_key, today)
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
                _unmark_fired(source_key, today)
                logger.info(
                    "Bỏ qua daily %s / %s — đang có yêu cầu khác xử lý",
                    source_key,
                    genre.label,
                )
            except Exception:
                logger.exception("Lỗi không mong đợi khi daily crawl %s / %s", source_key, genre.label)
                try:
                    db.rollback()
                except Exception:
                    pass
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

        if summaries:
            from crawl.application.notify import format_scan_summary, notify_configured

            notify_configured(db, title="Crawl daily xong", body=format_scan_summary(summaries))
    except Exception:
        logger.exception("Lỗi không mong đợi khi chạy lịch hàng ngày")
    finally:
        close_browser()
        db.close()


def run_follow_tick() -> list:
    """Kiểm tra lần lượt truyện theo dõi đã quá hạn. Truyện đang bị khoá (đang cào) để lượt sau."""
    from crawl.application.follow import check_follow, due_follows
    from crawl.application.notify import notify_configured

    db = SessionLocal()
    results = []
    try:
        for novel_id in due_follows(db, dt.datetime.utcnow()):
            lock_key = f"crawl-novel:{novel_id}"
            if not try_acquire(lock_key):
                continue
            try:
                results.append(check_follow(db, novel_id, source_resolver=get_source))
            except Exception:
                logger.exception("Lỗi khi kiểm tra truyện theo dõi %s", novel_id)
                db.rollback()
            finally:
                release(lock_key)
        fresh = [r for r in results if r.new_chapters > 0]
        if fresh:
            body = "\n".join(
                f"{r.title}: +{r.new_chapters} chương" + (" (đã gửi dịch)" if r.sent_to_translate else "")
                for r in fresh
            )
            notify_configured(db, title="Truyện theo dõi có chương mới", body=body)
    finally:
        close_browser()
        db.close()
    return results


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
            # Chạy ngay sau start — site quá giờ hẹn mà hôm nay chưa chạy sẽ bù luôn.
            next_run_time=dt.datetime.now(),
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_follow_tick, trigger="interval", minutes=15, id="follow_tick", max_instances=1, coalesce=True
        )
    return scheduler
