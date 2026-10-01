"""FastAPI router cho context Crawl — nhận HTTP request, gọi use case, trả
Pydantic response. Không chứa business logic (nằm ở application/domain).

Mọi repo/use case lấy qua `Depends(...)` thay vì tự khởi tạo trong từng
route — thêm route mới chỉ cần khai `= Depends(get_xxx)` trong tham số, và
đây cũng là chỗ duy nhất cần sửa nếu sau này đổi cách dựng use case (vd
thêm cache, đổi implementation)."""
import logging
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

# Ngoại lệ layering có chủ đích (khác mọi import khác trong file — routers.py
# không được biết SourcePort nào đang chạy thật): đây KHÔNG phải business
# logic, chỉ là dọn tài nguyên tiến trình (Chromium) đúng lúc 1 thread NỀN
# sắp chết — chỗ duy nhất trong toàn bộ codebase biết "job nền này xong
# thật chưa" (application/use_cases.py không biết gì về thread/tiến trình
# hệ điều hành). Xem browser_fetch.py mục docstring 17/9/2026.
from crawl.infrastructure.sources.browser_fetch import close_browser

from crawl.api.schemas import (
    AddNovelIn, BatchExportIn, ChapterContentIn, ChapterContentOut, ChapterListOut, ChapterOut,
    ChapterRetryOut,
    CrawlNovelResultOut, DeleteOut, DryRunIn, DryRunOut, FollowIn, FollowListOut, FollowOut,
    GenreListOut, GenreOut, GenreProgressOut, PipelineIn, PipelineListOut, PipelineOut,
    GenreToggleIn, NovelExportStatusOut, NovelListOut, NovelOut, RetryErrorsIn, RetryErrorsOut,
    ReviewAllOut, SendToTranslateIn, SendToTranslateOut, SettingsOut, SettingsPatchIn, SiteListOut,
    SiteSessionIn, SiteSessionOut, SiteSessionProbeOut, SmoothNovelIn, SmoothNovelOut,
    TranslateHandoffChapterOut, TranslateHandoffOut, TranslateLifecycleIn,
)
from crawl.application.use_cases import (
    AddManualNovelUseCase, CrawlGenreUseCase, CrawlNovelUseCase,
    DeleteChapterUseCase, DeleteNovelUseCase, DiscardChapterCleanedUseCase, DryRunUseCase,
    ForceAcceptNovelUseCase, GetChapterContentUseCase, NovelExportUseCase, RawTextStorage,
    RetryChapterUseCase, ReviewAllChaptersUseCase, SetActiveGenreUseCase, SmoothNovelUseCase,
    UpdateChapterContentUseCase,
)
from crawl.domain.entities import ChapterStatus, GenreRunStatus
from crawl.domain.ports import ChapterRepository, GenreRepository, NovelRepository
from crawl.infrastructure.persistence.models import NovelFollowModel, NovelPipelineModel
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository, SqlAlchemyGenreRepository, SqlAlchemyNovelRepository,
)
from crawl.infrastructure.sources.registry import SOURCES, catalog_genre_keys, get_source
from crawl.infrastructure.sources.site_access import SiteAccessKind, site_access_kind
from crawl.infrastructure.sources.site_regions import SiteRegion, site_region
from platform_.config import config
from platform_.db import SessionLocal, get_db
from platform_.locks import is_locked, release, try_acquire
from platform_.settings_store import get_all, get_per_site_int, get_per_site_setting, set_setting

logger = logging.getLogger("crawl")

router = APIRouter(prefix="/api/crawl", tags=["crawl"])


# --------------------------------------------------------- Dependencies --
# Provider cho từng repo/use case — route bên dưới chỉ khai báo phụ thuộc,
# không tự new() lên. Đổi implementation (vd thêm cache) chỉ sửa ở đây.

def get_novel_repo(db: Session = Depends(get_db)) -> NovelRepository:
    return SqlAlchemyNovelRepository(db)


def get_chapter_repo(db: Session = Depends(get_db)) -> ChapterRepository:
    return SqlAlchemyChapterRepository(db)


def get_genre_repo(db: Session = Depends(get_db)) -> GenreRepository:
    return SqlAlchemyGenreRepository(db)


def get_crawl_novel_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> CrawlNovelUseCase:
    from platform_.terminal_ui import report_progress

    return CrawlNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
        source_resolver=get_source,
        on_progress=report_progress,
    )


def get_crawl_genre_use_case(
    db: Session = Depends(get_db),
    novel_repo: NovelRepository = Depends(get_novel_repo),
    genre_repo: GenreRepository = Depends(get_genre_repo),
    crawl_novel_use_case: CrawlNovelUseCase = Depends(get_crawl_novel_use_case),
) -> CrawlGenreUseCase:
    from platform_.terminal_ui import report_progress

    return CrawlGenreUseCase(
        novel_repo=novel_repo,
        genre_repo=genre_repo,
        crawl_novel_use_case=crawl_novel_use_case,
        source_resolver=get_source,
        # Setting RIÊNG từng site (mục 9.0) — `source_key` chỉ biết được lúc
        # use case chạy (theo genre đang quét), không phải lúc dựng use case.
        get_scan_window=lambda source_key: get_per_site_int(db, "scan_window", source_key),
        get_max_chapters_per_story=lambda source_key: get_per_site_int(
            db, "max_chapters_per_story", source_key
        ),
        get_narration_filter=lambda source_key: get_per_site_setting(db, "narration_filter", source_key),
        get_max_pages_per_scan=lambda source_key: get_per_site_int(db, "max_pages_per_scan", source_key),
        get_max_consecutive_errors=lambda source_key: get_per_site_int(
            db, "max_consecutive_errors", source_key
        ),
        get_completion_filter=lambda source_key: get_per_site_setting(db, "completion_filter", source_key),
        on_progress=report_progress,
    )


def get_add_manual_novel_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    crawl_novel_use_case: CrawlNovelUseCase = Depends(get_crawl_novel_use_case),
) -> AddManualNovelUseCase:
    return AddManualNovelUseCase(
        novel_repo=novel_repo,
        crawl_novel_use_case=crawl_novel_use_case,
        source_resolver=get_source,
    )


def get_dry_run_use_case() -> DryRunUseCase:
    return DryRunUseCase(source_resolver=get_source)


def get_set_active_genre_use_case(
    genre_repo: GenreRepository = Depends(get_genre_repo),
) -> SetActiveGenreUseCase:
    return SetActiveGenreUseCase(genre_repo=genre_repo)


def get_chapter_content_use_case(
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> GetChapterContentUseCase:
    return GetChapterContentUseCase(chapter_repo=chapter_repo, storage=RawTextStorage(config.raw_dir))


def get_update_chapter_content_use_case(
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> UpdateChapterContentUseCase:
    return UpdateChapterContentUseCase(chapter_repo=chapter_repo, storage=RawTextStorage(config.raw_dir))


def get_discard_chapter_cleaned_use_case(
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> DiscardChapterCleanedUseCase:
    return DiscardChapterCleanedUseCase(chapter_repo=chapter_repo, storage=RawTextStorage(config.raw_dir))


def get_retry_chapter_use_case(
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
    novel_repo: NovelRepository = Depends(get_novel_repo),
) -> RetryChapterUseCase:
    return RetryChapterUseCase(
        chapter_repo=chapter_repo, novel_repo=novel_repo,
        storage=RawTextStorage(config.raw_dir), source_resolver=get_source,
    )


def get_smooth_novel_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
    db: Session = Depends(get_db),
) -> SmoothNovelUseCase:
    return SmoothNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
        get_opencc_mode=lambda sk: get_per_site_setting(db, "opencc_mode", sk) or "none",
    )


def get_delete_novel_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> DeleteNovelUseCase:
    return DeleteNovelUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
    )


def get_delete_chapter_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> DeleteChapterUseCase:
    return DeleteChapterUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
    )


def get_novel_export_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> NovelExportUseCase:
    return NovelExportUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
    )


def get_review_all_use_case(
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
) -> ReviewAllChaptersUseCase:
    return ReviewAllChaptersUseCase(
        novel_repo=novel_repo,
        chapter_repo=chapter_repo,
        storage=RawTextStorage(config.raw_dir),
    )


# ----------------------------------------------------------------- Sites --
# Mục 9.0 — trang "Danh sách site", vào từng site mới thấy chọn thể loại,
# Quét ngay, thêm truyện bằng URL, cài đặt RIÊNG của site đó (sửa 16/9/2026
# theo phản hồi "UI đang sai" khi định tích hợp nhiều site hơn).

@router.get("/sites", response_model=SiteListOut)
def list_sites(
    search: str | None = None,
    access_kind: SiteAccessKind | Literal["needs_session"] | None = None,
    region: SiteRegion | None = None,
    limit: int = 20,
    offset: int = 0,
):
    """Chỉ trả site THẬT (bỏ site nội bộ dùng để test — `SourcePort.is_test`,
    vd `demo_local` — không hữu ích với người dùng thật)."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    sites = [
        {
            "key": s.key,
            "name": s.name,
            "access_kind": site_access_kind(s.key),
            "region": site_region(s.key),
        }
        for s in SOURCES.values()
        if not s.is_test
    ]
    if search:
        needle = search.casefold()
        sites = [
            s for s in sites
            if needle in s["key"].casefold() or needle in s["name"].casefold()
        ]
    if access_kind == "needs_session":
        sites = [s for s in sites if s["access_kind"] != "free"]
    elif access_kind is not None:
        sites = [s for s in sites if s["access_kind"] == access_kind]
    if region is not None:
        sites = [s for s in sites if s["region"] == region]
    total = len(sites)
    return {"items": sites[offset : offset + limit], "total": total}


@router.get("/sites/{source_key}/session", response_model=SiteSessionOut)
def get_site_session(source_key: str, db: Session = Depends(get_db)):
    if source_key not in SOURCES:
        raise HTTPException(404, f"Không có site '{source_key}'")
    from platform_.session_cookies import session_status

    return session_status(source_key, db=db)


@router.put("/sites/{source_key}/session", response_model=SiteSessionOut)
def put_site_session(source_key: str, body: SiteSessionIn, db: Session = Depends(get_db)):
    """Lưu cookie phiên do user đăng nhập tay trên trình duyệt rồi dán vào."""
    if source_key not in SOURCES:
        raise HTTPException(404, f"Không có site '{source_key}'")
    from platform_.session_cookies import save_cookie_header, session_status

    save_cookie_header(source_key, body.cookie_header, db=db)
    return session_status(source_key, db=db)


@router.post("/sites/{source_key}/session/probe", response_model=SiteSessionProbeOut)
def probe_site_session(source_key: str):
    """Thử GET trang chủ site với cookie đã lưu — xem còn bị chặn / verify không."""
    if source_key not in SOURCES:
        raise HTTPException(404, f"Không có site '{source_key}'")
    source = SOURCES[source_key]
    base_url = getattr(getattr(source, "cfg", None), "base_url", None)
    if not base_url:
        return SiteSessionProbeOut(
            ok=False,
            message="Site này không dùng HTTP HTML (vd demo cục bộ) — không probe được.",
            cookie_configured=False,
        )
    from platform_.session_cookies import load_cookie_header, session_status

    status = session_status(source_key)
    cookie_header = status.get("cookie_header") or load_cookie_header(source_key)
    missing = list(status.get("missing_required_cookies") or [])
    if missing:
        return SiteSessionProbeOut(
            ok=False,
            cookie_configured=bool(cookie_header),
            missing_required_cookies=missing,
            message=(
                f"Cookie thiếu bắt buộc: {', '.join(missing)}. "
                "Đăng nhập lại trên trình duyệt → copy nguyên Cookie header → Lưu."
            ),
        )
    try:
        soup = source._get_soup(base_url)  # noqa: SLF001 — probe nội bộ
        title_node = soup.select_one("title")
        title = title_node.get_text(strip=True) if title_node else ""
        text_sample = soup.get_text(" ", strip=True)[:2000].lower()
        block_markers = [
            "just a moment", "cloudflare", "captcha", "verify", "加载中",
            "请稍后", "访问频繁", "attention required", "请先登录", "登录知乎",
        ]
        looks_blocked = any(m in text_sample or m in title.lower() for m in block_markers)
        if looks_blocked:
            return SiteSessionProbeOut(
                ok=False,
                final_url=base_url,
                http_status=200,
                page_title=title or None,
                looks_blocked=True,
                cookie_configured=bool(cookie_header),
                missing_required_cookies=[],
                message=(
                    "Vẫn giống trang chặn/verify/login. Thử đăng nhập lại trên trình duyệt, "
                    "copy cookie mới (hoặc cần tầng browser — làm sau)."
                ),
            )
        return SiteSessionProbeOut(
            ok=True,
            final_url=base_url,
            http_status=200,
            page_title=title or None,
            looks_blocked=False,
            cookie_configured=bool(cookie_header),
            missing_required_cookies=[],
            message="Trang chủ tải được với phiên hiện tại.",
        )
    except Exception as exc:
        return SiteSessionProbeOut(
            ok=False,
            cookie_configured=bool(cookie_header),
            missing_required_cookies=missing,
            message=f"Probe thất bại: {exc}",
        )


# ---------------------------------------------------------------- Genres --

@router.get("/genres", response_model=GenreListOut)
def list_genres(
    source_key: str | None = None,
    search: str | None = None,
    enabled: bool | None = None,
    last_run_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    genre_repo: GenreRepository = Depends(get_genre_repo),
):
    """Chỉ trả option đang nằm trong GENRE_SEEDS (catalog) — select FE =
    đúng thể loại thật của site, không hiện option cũ đã bỏ (vd *_hot)."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    allowed = catalog_genre_keys()
    items = genre_repo.list_filtered(
        source_key=source_key,
        search=search,
        enabled=enabled,
        last_run_status=last_run_status,
        allowed_keys=allowed,
        limit=limit,
        offset=offset,
    )
    total = genre_repo.count_filtered(
        source_key=source_key,
        search=search,
        enabled=enabled,
        last_run_status=last_run_status,
        allowed_keys=allowed,
    )
    return {"items": items, "total": total}


@router.patch("/genres/{genre_id}", response_model=GenreOut)
def toggle_genre(
    genre_id: int,
    body: GenreToggleIn,
    genre_repo: GenreRepository = Depends(get_genre_repo),
    set_active_use_case: SetActiveGenreUseCase = Depends(get_set_active_genre_use_case),
):
    """`enabled=true` chọn thể loại này làm "active" cho SITE của nó — tự
    tắt các thể loại khác cùng site (khớp UI select box mỗi site 1 lựa
    chọn, mục 9.2). `enabled=false` chỉ tắt riêng thể loại này, không đụng
    thể loại khác (dùng khi muốn 1 site không quét gì cả)."""
    if body.enabled:
        genre = set_active_use_case.execute(genre_id)
        if genre is None:
            raise HTTPException(404, "Không tìm thấy thể loại")
        return genre
    genre = genre_repo.get_by_id(genre_id)
    if genre is None:
        raise HTTPException(404, "Không tìm thấy thể loại")
    genre.enabled = False
    genre_repo.update(genre)
    return genre_repo.get_by_id(genre_id)


@router.post("/genres/{genre_id}/run-now", response_model=GenreOut, status_code=202)
def run_genre_now(genre_id: int, genre_repo: GenreRepository = Depends(get_genre_repo)):
    """Chạy NỀN (thread riêng) thay vì chờ trong request — quét thật có thể
    mất nhiều phút (nhiều truyện x nhiều chương, retry khi site chậm), giữ
    request chờ suốt lúc đó dễ timeout phía trình duyệt và không cho người
    dùng thấy gì đang diễn ra nếu họ lỡ tải lại trang. Trả về ngay Genre ở
    trạng thái "running" (202) — FE poll `GET /genres` để thấy running ->
    done/error + kết quả khi xong (Genre.last_run_*, mục 9.2).

    Khoá theo genre_id (dùng CHUNG key với job lịch trong scheduler.py) —
    chặn bấm "Quét ngay" 2 lần liên tiếp, hoặc bấm đúng lúc job lịch đang
    chạy cùng thể loại (platform_/locks.py). Khoá được GIỮ tới khi thread
    nền xong việc (không nhả ngay khi request này trả về)."""
    genre = genre_repo.get_by_id(genre_id)
    if genre is None:
        raise HTTPException(404, "Không tìm thấy thể loại")
    lock_key = f"genre-run:{genre_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{lock_key}', vui lòng đợi rồi thử lại")

    genre.mark_run_started()
    genre_repo.update_run_state(genre)
    threading.Thread(target=_run_genre_in_background, args=(genre_id, lock_key), daemon=True).start()
    return genre_repo.get_by_id(genre_id)


@router.get("/genres/{genre_id}/progress")
def get_genre_progress(genre_id: int, genre_repo: GenreRepository = Depends(get_genre_repo)):
    """Tiến độ live của lượt quét đang chạy (in-memory). `progress=null` nếu
    chưa có snapshot — FE vẫn dựa vào last_run_status=running."""
    genre = genre_repo.get_by_id(genre_id)
    if genre is None:
        raise HTTPException(404, "Không tìm thấy thể loại")
    from platform_.run_progress import as_api_dict, get_genre

    data = as_api_dict(get_genre(genre_id))
    return {"progress": GenreProgressOut(**data) if data else None}


@router.post("/genres/{genre_id}/cancel", response_model=GenreOut)
def cancel_genre_run(genre_id: int, genre_repo: GenreRepository = Depends(get_genre_repo)):
    """Yêu cầu dừng lượt quét đang chạy nền. Scan loop check cờ giữa các
    ứng viên/chương — có thể mất vài giây tới khi HTTP đang chờ xong."""
    genre = genre_repo.get_by_id(genre_id)
    if genre is None:
        raise HTTPException(404, "Không tìm thấy thể loại")
    if genre.last_run_status != GenreRunStatus.RUNNING:
        raise HTTPException(409, "Không có lượt quét đang chạy để dừng")
    if not is_locked(f"genre-run:{genre_id}"):
        # Không thread nào giữ khoá: RUNNING là trạng thái mồ côi, không còn ai để nhận cờ dừng.
        genre.mark_run_finished(
            status=GenreRunStatus.CANCELLED, discovered=0, rejected=0, errors=0,
            messages=["Đã dừng: không còn lượt quét nào chạy thật"],
        )
        genre_repo.update_run_state(genre)
        return genre_repo.get_by_id(genre_id)
    from platform_.run_cancel import request_cancel

    request_cancel(genre_id)
    return genre


def _notify_genre_run(db: Session, genre_repo: GenreRepository, genre_id: int, result) -> None:
    """Webhook khi "Quét ngay" xong — cùng format với lịch hàng ngày; chỉ gửi
    khi đã cấu hình notify.webhook_url."""
    from crawl.application.notify import format_scan_summary, notify_configured

    try:
        genre = genre_repo.get_by_id(genre_id)
        summary = {
            "source_key": genre.source_key if genre else "?",
            "genre_label": genre.label if genre else str(genre_id),
            "discovered": result.discovered,
            "synced": result.synced,
            "rejected": result.rejected,
            "errors": result.errors,
        }
        title = "Quét ngay đã dừng" if result.cancelled else "Quét ngay xong"
        notify_configured(db, title=title, body=format_scan_summary([summary]))
    except Exception:
        logger.exception("Không gửi được webhook cho genre %s", genre_id)


def _notify_novel_failure(db: Session, novel_id: int, result) -> None:
    """Webhook khi crawl 1 truyện (Thử lại / thêm tay / force-accept) thất bại."""
    if result is None or result.success or getattr(result, "cancelled", False):
        return
    from crawl.application.notify import notify_configured

    try:
        novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
        name = f"#{novel_id} {novel.title}" if novel else f"#{novel_id}"
        notify_configured(db, title="Crawl truyện lỗi", body=f"{name}: {result.error or 'lỗi không rõ'}")
    except Exception:
        logger.exception("Không gửi được webhook lỗi crawl novel %s", novel_id)


def _mark_genre_crashed(genre_id: int, exc: Exception) -> None:
    """Thread chết ngoài execute thì genre còn RUNNING mãi, nút quét bị khoá."""
    db = SessionLocal()
    try:
        repo = SqlAlchemyGenreRepository(db)
        genre = repo.get_by_id(genre_id)
        if genre is None or genre.last_run_status != GenreRunStatus.RUNNING:
            return
        genre.mark_run_finished(
            status=GenreRunStatus.ERROR,
            discovered=0,
            rejected=0,
            errors=1,
            messages=[f"Lỗi khi chạy nền: {exc}"[:500]],
        )
        repo.update_run_state(genre)
    except Exception:
        logger.exception("Không ghi được trạng thái error cho genre %s", genre_id)
    finally:
        db.close()


def _mark_novel_crashed(novel_id: int, exc: Exception) -> None:
    """Thread chết trước/ngoài execute thì truyện còn CRAWLING mãi, không xoá được."""
    from crawl.domain.entities import NovelLifecycle

    db = SessionLocal()
    try:
        repo = SqlAlchemyNovelRepository(db)
        novel = repo.get_by_id(novel_id)
        if novel is None or novel.lifecycle_status != NovelLifecycle.CRAWLING:
            return
        novel.mark_error(f"Lỗi khi crawl nền: {exc}"[:500])
        repo.update(novel)
    except Exception:
        logger.exception("Không ghi được trạng thái error cho novel %s", novel_id)
    finally:
        db.close()


def _run_genre_in_background(genre_id: int, lock_key: str) -> None:
    """Chạy trong thread riêng -> PHẢI tự mở Session/repo riêng (session của
    request gốc đã đóng ngay khi request đó trả response). Tự đảm bảo nhả
    khoá dù crawl lỗi bất ngờ (try/finally), tránh kẹt khoá vĩnh viễn."""
    db = SessionLocal()
    try:
        genre_repo = SqlAlchemyGenreRepository(db)
        use_case = get_crawl_genre_use_case(
            db=db,
            novel_repo=SqlAlchemyNovelRepository(db),
            genre_repo=genre_repo,
            crawl_novel_use_case=get_crawl_novel_use_case(
                novel_repo=SqlAlchemyNovelRepository(db), chapter_repo=SqlAlchemyChapterRepository(db)
            ),
        )
        result = use_case.execute(genre_id)  # tự lưu last_run_* khi xong (kể cả khi lỗi)
        _notify_genre_run(db, genre_repo, genre_id, result)
    except Exception as exc:
        logger.exception("Lỗi không mong đợi khi chạy nền genre %s", genre_id)
        try:
            db.rollback()
        except Exception:
            pass
        _mark_genre_crashed(genre_id, exc)
    finally:
        close_browser()  # đóng Chromium của thread này nếu đã mở — mục 4c
        db.close()
        release(lock_key)


# ---------------------------------------------------------------- Novels --

def _novels_out(novels: list, chapter_repo: ChapterRepository) -> list[NovelOut]:
    """Domain Novel -> NovelOut kèm đếm chương crawled/failed (1 query)."""
    from crawl.application.use_cases import DONE_CHAPTER_STATUSES

    done = {s.value for s in DONE_CHAPTER_STATUSES}
    counts = chapter_repo.count_status_by_novels([n.id for n in novels if n.id is not None])
    out: list[NovelOut] = []
    for n in novels:
        by_status = counts.get(n.id, {})
        out.append(
            NovelOut.model_validate(n).model_copy(
                update={
                    "crawled_chapters": sum(v for k, v in by_status.items() if k in done),
                    "failed_chapters": by_status.get(ChapterStatus.FAILED.value, 0),
                }
            )
        )
    return out


@router.get("/novels", response_model=NovelListOut)
def list_novels(
    status: str | None = None,
    source_key: str | None = None,
    search: str | None = None,
    is_manual: bool | None = None,
    genre_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
):
    """Phân trang + lọc theo site / trạng thái / thể loại quét / tay-vs-quét."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    items = novel_repo.list_all(
        status=status,
        source_key=source_key,
        search=search,
        is_manual=is_manual,
        genre_id=genre_id,
        limit=limit,
        offset=offset,
    )
    total = novel_repo.count_all(
        status=status,
        source_key=source_key,
        search=search,
        is_manual=is_manual,
        genre_id=genre_id,
    )
    return {"items": _novels_out(items, chapter_repo), "total": total}


@router.get("/novels/{novel_id}", response_model=NovelOut)
def get_novel(
    novel_id: int,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
):
    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    return _novels_out([novel], chapter_repo)[0]


@router.get("/novels/{novel_id}/progress")
def get_novel_progress(novel_id: int, novel_repo: NovelRepository = Depends(get_novel_repo)):
    """Tiến độ live khi crawl 1 truyện (Thử lại / thêm tay / force-accept) —
    snapshot in-memory `novel:{id}`, cùng shape với /genres/{id}/progress.
    `progress=null` nếu chưa/không có lượt chạy nào trong tiến trình này."""
    if novel_repo.get_by_id(novel_id) is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    from platform_.run_progress import as_api_dict, get

    data = as_api_dict(get(f"novel:{novel_id}"))
    return {"progress": GenreProgressOut(**data) if data else None}


@router.get("/novels/{novel_id}/translate-handoff", response_model=TranslateHandoffOut)
def get_translate_handoff(
    novel_id: int,
    prefer_cleaned: bool = True,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
):
    """Phase 0 contract — payload để translate-service tạo Work (không share DB).

    Ưu tiên cleaned text; trả fingerprint + cờ gate (missing_cleaned / unreviewed).
    """
    from crawl.application.fingerprint import content_fingerprint
    from crawl.domain.entities import ChapterStatus
    from crawl.infrastructure.sources.registry import SOURCES

    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")

    source = SOURCES.get(novel.source_key)
    cfg = getattr(source, "cfg", None) if source is not None else None
    lang_src = getattr(cfg, "content_locale", "zh") if cfg else "zh"

    storage = RawTextStorage(config.raw_dir)
    chapters = chapter_repo.list_by_novel_filtered(
        novel_id, status=ChapterStatus.CRAWLED.value, limit=None, offset=0
    )
    out_chapters: list[TranslateHandoffChapterOut] = []
    missing_cleaned = 0
    unreviewed = 0
    for ch in chapters:
        if not ch.raw_path:
            continue
        has_cleaned = storage.has_cleaned(ch.raw_path)
        if not has_cleaned:
            missing_cleaned += 1
        if not ch.reviewed:
            unreviewed += 1
        try:
            raw = storage.read(ch.raw_path)
        except OSError:
            continue
        text = raw
        if prefer_cleaned and has_cleaned:
            try:
                text = storage.read(storage.cleaned_path_for(ch.raw_path))
            except OSError:
                text = raw
        out_chapters.append(
            TranslateHandoffChapterOut(
                index=ch.chapter_index,
                title=ch.title,
                text=text,
                fingerprint=content_fingerprint(text),
                has_cleaned=has_cleaned,
                reviewed=bool(ch.reviewed),
                crawl_chapter_id=ch.id,
                order=ch.sort_key[0],
            )
        )

    if not out_chapters:
        raise HTTPException(400, "Truyện chưa có chương crawled nào để handoff")

    return TranslateHandoffOut(
        external_id=f"crawl:novel:{novel.id}",
        title=novel.title,
        author=novel.author or "",
        lang_src=lang_src,
        lang_tgt_hint="vi",
        source_key=novel.source_key,
        source_url=novel.source_url,
        chapters=out_chapters,
        missing_cleaned=missing_cleaned,
        unreviewed=unreviewed,
    )


@router.post("/novels/{novel_id}/send-to-translate", response_model=SendToTranslateOut)
def send_novel_to_translate(
    novel_id: int,
    body: SendToTranslateIn | None = None,
    db: Session = Depends(get_db),
):
    """P2 — crawl gọi translate from-crawl (+ optional start job) rồi mark translating."""
    from crawl.application.send_to_translate import send_to_translate

    opts = body or SendToTranslateIn()
    try:
        result = send_to_translate(
            db,
            novel_id=novel_id,
            require_cleaned=opts.require_cleaned,
            start_job=opts.start_job,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result.error:
        # Work đã tạo + novel đã đánh dấu translating, chỉ start job lỗi.
        raise HTTPException(502, result.error)
    return SendToTranslateOut(
        novel_id=novel_id,
        lifecycle_status=result.novel.lifecycle_status.value,
        work_id=result.work_id,
        variant_id=result.variant_id,
        job_id=result.job_id,
        missing_cleaned=result.missing_cleaned,
        unreviewed=result.unreviewed,
        translate_path=f"/translate/{result.work_id}",
        warnings=result.warnings,
    )


@router.post("/novels/{novel_id}/translate-lifecycle", response_model=NovelOut)
def translate_lifecycle_callback(
    novel_id: int,
    body: TranslateLifecycleIn,
    db: Session = Depends(get_db),
):
    """Callback từ translate-service — cập nhật translating / ready_for_video / failed."""
    from crawl.application.send_to_translate import apply_translate_lifecycle

    try:
        novel = apply_translate_lifecycle(
            db, novel_id=novel_id, status=body.status, message=body.message
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from crawl.application.pipeline import on_translate_status

    on_translate_status(db, novel_id, body.status, body.message)
    from crawl.application.follow import on_follow_audio

    on_follow_audio(db, novel_id, body.status)
    return novel


@router.get("/novels/{novel_id}/chapters", response_model=ChapterListOut)
def list_novel_chapters(
    novel_id: int,
    status: str | None = None,
    search: str | None = None,
    reviewed: bool | None = None,
    has_cleaned: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    chapter_repo: ChapterRepository = Depends(get_chapter_repo),
):
    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    storage = RawTextStorage(config.raw_dir)

    if has_cleaned is None:
        items = chapter_repo.list_by_novel_filtered(
            novel_id,
            status=status,
            search=search,
            reviewed=reviewed,
            limit=limit,
            offset=offset,
        )
        total = chapter_repo.count_by_novel_filtered(
            novel_id, status=status, search=search, reviewed=reviewed
        )
    else:
        # has_cleaned nằm trên disk — lọc sau query DB rồi mới phân trang.
        candidates = chapter_repo.list_by_novel_filtered(
            novel_id,
            status=status,
            search=search,
            reviewed=reviewed,
            limit=None,
            offset=0,
        )
        filtered = [
            ch
            for ch in candidates
            if bool(ch.raw_path and storage.has_cleaned(ch.raw_path)) is has_cleaned
        ]
        total = len(filtered)
        items = filtered[offset : offset + limit]

    out_items: list[ChapterOut] = []
    for ch in items:
        chapter_has_cleaned = bool(ch.raw_path and storage.has_cleaned(ch.raw_path))
        out_items.append(
            ChapterOut(
                id=ch.id,
                chapter_index=ch.chapter_index,
                title=ch.title,
                status=ch.status.value if hasattr(ch.status, "value") else str(ch.status),
                error_message=ch.error_message,
                reviewed=ch.reviewed,
                has_cleaned=chapter_has_cleaned,
                toc_order=ch.toc_order,
            )
        )
    return {"items": out_items, "total": total}


def _crawl_novel_in_background(novel_id: int, lock_key: str, *, incremental: bool = False) -> None:
    """Thread nền crawl 1 novel — session riêng (request gốc đã đóng), luôn nhả khoá."""
    db = SessionLocal()
    try:
        use_case = get_crawl_novel_use_case(
            novel_repo=SqlAlchemyNovelRepository(db),
            chapter_repo=SqlAlchemyChapterRepository(db),
        )
        result = use_case.execute(novel_id, incremental=incremental)
        _notify_novel_failure(db, novel_id, result)
    except Exception as exc:
        logger.exception("Lỗi không mong đợi khi crawl nền novel %s", novel_id)
        try:
            db.rollback()
        except Exception:
            pass
        _mark_novel_crashed(novel_id, exc)
    finally:
        close_browser()  # đóng Chromium của thread này nếu đã mở — mục 4c
        db.close()
        release(lock_key)


@router.post("/novels", response_model=CrawlNovelResultOut)
def add_novel(
    body: AddNovelIn,
    response: Response,
    use_case: AddManualNovelUseCase = Depends(get_add_manual_novel_use_case),
):
    """Validate + tạo Novel đồng bộ; crawl chạy NỀN (202) — tránh giữ
    threadpool API hàng phút (giống /genres/.../run-now)."""
    from crawl.domain.urls import normalize_novel_url

    lock_key = f"add-novel:{body.source_key}:{normalize_novel_url(body.url) or body.url}"
    if not try_acquire(lock_key):
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{lock_key}', vui lòng đợi rồi thử lại")
    try:
        result = use_case.execute(body.source_key, body.url, start_crawl=False)
    except Exception:
        release(lock_key)
        raise
    if not result.success:
        release(lock_key)
        response.status_code = 200
        return result

    crawl_lock = f"crawl-novel:{result.novel_id}"
    if not try_acquire(crawl_lock):
        release(lock_key)
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{crawl_lock}', vui lòng đợi rồi thử lại")
    release(lock_key)  # URL-lock chỉ cần đến khi đã có novel_id
    _mark_novel_crawling(result.novel_id)
    threading.Thread(
        target=_crawl_novel_in_background, args=(result.novel_id, crawl_lock), daemon=True
    ).start()
    response.status_code = 202
    return result


def _mark_novel_crawling(novel_id: int, *, incremental: bool = False) -> bool:
    """Đánh dấu crawling ngay để FE poll thấy tiến độ trước khi thread nền chạy.
    Trả True nếu đánh dấu được."""
    db = SessionLocal()
    try:
        repo = SqlAlchemyNovelRepository(db)
        novel = repo.get_by_id(novel_id)
        if novel is None:
            return False
        try:
            if incremental:
                novel.start_incremental_crawl()
            else:
                novel.start_crawling()
        except Exception:
            return False
        repo.update(novel)
        return True
    finally:
        db.close()


@router.post("/novels/{novel_id}/retry", response_model=CrawlNovelResultOut)
def retry_novel(novel_id: int, response: Response, novel_repo: NovelRepository = Depends(get_novel_repo)):
    """Resume (error) hoặc sync chương mới (fully_crawled) — chạy nền (202)."""
    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    from crawl.domain.entities import NovelLifecycle

    if novel.lifecycle_status not in (NovelLifecycle.ERROR, NovelLifecycle.FULLY_CRAWLED):
        raise HTTPException(
            400,
            f"Chỉ retry được truyện error/fully_crawled (hiện: {novel.lifecycle_status.value})",
        )
    incremental = True  # error resume + fully_crawled sync đều dùng incremental
    lock_key = f"crawl-novel:{novel_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{lock_key}', vui lòng đợi rồi thử lại")
    if not _mark_novel_crawling(novel_id, incremental=incremental):
        release(lock_key)
        raise HTTPException(400, "Không thể chuyển sang trạng thái crawling")
    threading.Thread(
        target=_crawl_novel_in_background,
        args=(novel_id, lock_key),
        kwargs={"incremental": incremental},
        daemon=True,
    ).start()
    response.status_code = 202
    return CrawlNovelResultOut(novel_id=novel_id, chapters_crawled=0, success=True, error=None)


def _follow_out(db: Session, row: NovelFollowModel) -> FollowOut | None:
    novel = SqlAlchemyNovelRepository(db).get_by_id(row.novel_id)
    if novel is None:
        return None
    return FollowOut(
        novel_id=row.novel_id,
        title=novel.title,
        lifecycle_status=novel.lifecycle_status.value,
        total_chapters=novel.total_chapters,
        auto_translate=bool(row.auto_translate),
        auto_audio=bool(row.auto_audio),
        voice_preset=row.voice_preset or "nam_ke",
        tts_work_id=row.tts_work_id,
        last_checked_at=row.last_checked_at,
        last_new_chapters=row.last_new_chapters or 0,
        last_error=row.last_error,
        checking=is_locked(f"follow-check:{row.novel_id}"),
    )


def _pipeline_out(db: Session, row: NovelPipelineModel) -> PipelineOut | None:
    novel = SqlAlchemyNovelRepository(db).get_by_id(row.novel_id)
    if novel is None:
        return None
    return PipelineOut(
        novel_id=row.novel_id,
        title=novel.title,
        stage=row.stage,
        voice_preset=row.voice_preset,
        engine=row.engine,
        translate_work_id=row.translate_work_id,
        tts_work_id=row.tts_work_id,
        error=row.error,
    )


def _pipeline_thread(novel_id: int, lock_key: str) -> None:
    from crawl.application.pipeline import execute

    db = SessionLocal()
    try:
        execute(db, novel_id)
    except Exception:
        logger.exception("Lỗi khi chạy pipeline novel %s", novel_id)
        from crawl.application.pipeline import _fail

        _fail(db, novel_id, "Lỗi không mong đợi khi chạy chuỗi")
    finally:
        db.close()
        release(lock_key)


@router.get("/pipelines", response_model=PipelineListOut)
def list_pipelines(db: Session = Depends(get_db)):
    rows = db.query(NovelPipelineModel).order_by(NovelPipelineModel.updated_at.desc()).all()
    return PipelineListOut(items=[out for row in rows if (out := _pipeline_out(db, row)) is not None])


@router.post("/novels/{novel_id}/pipeline", response_model=PipelineOut, status_code=202)
def start_pipeline(novel_id: int, body: PipelineIn, db: Session = Depends(get_db)):
    from crawl.application.pipeline import PipelineBusy, begin

    lock_key = f"pipeline:{novel_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, "Chuỗi này đang chạy")
    try:
        row = begin(db, novel_id, voice_preset=body.voice_preset, engine=body.engine)
    except LookupError as exc:
        release(lock_key)
        raise HTTPException(404, str(exc)) from exc
    except PipelineBusy as exc:
        release(lock_key)
        raise HTTPException(409, "Chuỗi này đang chạy") from exc
    except ValueError as exc:
        release(lock_key)
        raise HTTPException(400, str(exc)) from exc
    threading.Thread(target=_pipeline_thread, args=(novel_id, lock_key), daemon=True).start()
    return _pipeline_out(db, row)


@router.get("/follows", response_model=FollowListOut)
def list_follows(db: Session = Depends(get_db)):
    rows = db.query(NovelFollowModel).order_by(NovelFollowModel.created_at.desc()).all()
    return FollowListOut(items=[out for row in rows if (out := _follow_out(db, row)) is not None])


@router.put("/novels/{novel_id}/follow", response_model=FollowOut)
def follow_novel(novel_id: int, body: FollowIn, db: Session = Depends(get_db)):
    if SqlAlchemyNovelRepository(db).get_by_id(novel_id) is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    from crawl.application.pipeline import PRESETS

    row = db.get(NovelFollowModel, novel_id) or NovelFollowModel(novel_id=novel_id)
    preset = (body.voice_preset or "nam_ke").strip()
    if preset not in PRESETS:
        raise HTTPException(400, "Preset giọng không hợp lệ")
    row.auto_translate = body.auto_translate
    row.auto_audio = body.auto_audio
    row.voice_preset = preset
    db.add(row)
    db.commit()
    return _follow_out(db, row)


@router.delete("/novels/{novel_id}/follow", status_code=204)
def unfollow_novel(novel_id: int, db: Session = Depends(get_db)):
    row = db.get(NovelFollowModel, novel_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


def _check_follow_in_background(novel_id: int, lock_key: str, check_key: str) -> None:
    from crawl.application.follow import check_follow

    db = SessionLocal()
    try:
        check_follow(db, novel_id, source_resolver=get_source)
    except Exception:
        logger.exception("Lỗi khi kiểm tra truyện theo dõi %s", novel_id)
    finally:
        close_browser()
        db.close()
        release(check_key)
        release(lock_key)


@router.post("/novels/{novel_id}/follow/check", response_model=FollowOut, status_code=202)
def check_follow_now(novel_id: int, db: Session = Depends(get_db)):
    row = db.get(NovelFollowModel, novel_id)
    if row is None:
        raise HTTPException(404, "Truyện chưa được theo dõi")
    lock_key = f"crawl-novel:{novel_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, "Truyện đang được cào, thử lại sau")
    check_key = f"follow-check:{novel_id}"
    try_acquire(check_key)
    threading.Thread(
        target=_check_follow_in_background, args=(novel_id, lock_key, check_key), daemon=True
    ).start()
    return _follow_out(db, row)


@router.post("/novels/retry-errors", response_model=RetryErrorsOut, status_code=202)
def retry_error_novels(body: RetryErrorsIn, novel_repo: NovelRepository = Depends(get_novel_repo)):
    """Sau khi cập nhật cookie: xếp hàng retry mọi novel `error` của site
    (lỗ VIP/nội dung). Chạy tuần tự trong 1 thread nền — tránh đập site."""
    if body.source_key not in SOURCES:
        raise HTTPException(404, f"Nguồn '{body.source_key}' không hỗ trợ")
    limit = max(1, min(body.limit, 200))
    novels = novel_repo.list_all(
        status="error",
        source_key=body.source_key,
        is_manual=body.is_manual,
        genre_id=body.genre_id,
        limit=limit,
        offset=0,
    )
    jobs: list[tuple[int, str]] = []
    skipped = 0
    for novel in novels:
        assert novel.id is not None
        lock_key = f"crawl-novel:{novel.id}"
        if not try_acquire(lock_key):
            skipped += 1
            continue
        if not _mark_novel_crawling(novel.id, incremental=True):
            release(lock_key)
            skipped += 1
            continue
        jobs.append((novel.id, lock_key))

    if jobs:
        threading.Thread(
            target=_retry_errors_sequential,
            args=(jobs,),
            daemon=True,
        ).start()

    return RetryErrorsOut(
        queued=len(jobs),
        skipped=skipped,
        novel_ids=[nid for nid, _ in jobs],
    )


def _retry_errors_sequential(jobs: list[tuple[int, str]]) -> None:
    """Crawl lần lượt — mỗi job đã acquire lock + mark crawling sẵn."""
    for novel_id, lock_key in jobs:
        _crawl_novel_in_background(novel_id, lock_key, incremental=True)


@router.post("/novels/{novel_id}/force-accept", response_model=CrawlNovelResultOut)
def force_accept_novel(
    novel_id: int,
    response: Response,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    crawl_novel_use_case: CrawlNovelUseCase = Depends(get_crawl_novel_use_case),
):
    """Force-accept đồng bộ; crawl chạy nền (202)."""
    use_case = ForceAcceptNovelUseCase(novel_repo=novel_repo, crawl_novel_use_case=crawl_novel_use_case)
    lock_key = f"crawl-novel:{novel_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{lock_key}', vui lòng đợi rồi thử lại")
    try:
        result = use_case.execute(novel_id, start_crawl=False)
    except Exception:
        release(lock_key)
        raise
    if not result.success:
        release(lock_key)
        response.status_code = 200
        return result
    _mark_novel_crawling(novel_id)
    threading.Thread(
        target=_crawl_novel_in_background, args=(novel_id, lock_key), daemon=True
    ).start()
    response.status_code = 202
    return result


@router.post("/novels/{novel_id}/smooth", response_model=SmoothNovelOut)
def smooth_novel(
    novel_id: int,
    body: SmoothNovelIn | None = None,
    use_case: SmoothNovelUseCase = Depends(get_smooth_novel_use_case),
):
    """Làm mượt rule — `chapter_ids` rỗng/null = tất cả; có list = chỉ chọn.
    Ghi data/cleaned/, không đè raw. Kỹ thuật novel-processor (MIT)."""
    chapter_ids = body.chapter_ids if body is not None else None
    force = bool(body.force) if body is not None else False
    result = use_case.execute(novel_id, chapter_ids=chapter_ids or None, force=force)
    if not result.success:
        raise HTTPException(400, result.error or "Không làm mượt được")
    return result


@router.delete("/novels/{novel_id}", response_model=DeleteOut)
def delete_novel(
    novel_id: int,
    use_case: DeleteNovelUseCase = Depends(get_delete_novel_use_case),
):
    """Xóa truyện + chương + file raw/cleaned. Chặn khi đang crawl."""
    lock_key = f"crawl-novel:{novel_id}"
    if not try_acquire(lock_key):
        raise HTTPException(409, f"Đang có yêu cầu khác xử lý '{lock_key}', vui lòng đợi rồi thử lại")
    try:
        result = use_case.execute(novel_id)
    finally:
        release(lock_key)
    if not result.success:
        code = 400 if result.error and "Không tìm thấy" not in result.error else 404
        raise HTTPException(code, result.error)
    return result


@router.get("/novels/{novel_id}/export-status", response_model=NovelExportStatusOut)
def novel_export_status(
    novel_id: int,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    status = use_case.status(novel_id)
    if status is None:
        raise HTTPException(404, "Không tìm thấy novel")
    return status


@router.get("/novels/{novel_id}/export.xlsx")
def export_novel_workbook(
    novel_id: int,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    """Xuất Excel — cột tiêu đề chương + nội dung (ưu tiên cleaned)."""
    from crawl.application.excel_export import content_disposition

    data, filename, error = use_case.export_workbook(novel_id)
    if error:
        raise HTTPException(400 if "Không tìm thấy" not in error else 404, error)
    assert data is not None and filename is not None
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": content_disposition(
                filename, fallback=f"novel-{novel_id}.xlsx"
            )
        },
    )


@router.get("/novels/{novel_id}/export.txt")
def export_novel_txt(
    novel_id: int,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    from crawl.application.excel_export import content_disposition

    data, filename, error = use_case.export_txt(novel_id)
    if error:
        raise HTTPException(400 if "Không tìm thấy" not in error else 404, error)
    assert data is not None and filename is not None
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(filename, fallback=f"novel-{novel_id}.txt")
        },
    )


@router.get("/novels/{novel_id}/export.epub")
def export_novel_epub(
    novel_id: int,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    from crawl.application.excel_export import content_disposition

    data, filename, error = use_case.export_epub(novel_id)
    if error:
        raise HTTPException(400 if "Không tìm thấy" not in error else 404, error)
    assert data is not None and filename is not None
    return Response(
        content=data,
        media_type="application/epub+zip",
        headers={
            "Content-Disposition": content_disposition(filename, fallback=f"novel-{novel_id}.epub")
        },
    )


@router.get("/novels/{novel_id}/export.zip")
def export_novel_bundle(
    novel_id: int,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    """Zip TXT + EPUB + XLSX."""
    from crawl.application.excel_export import content_disposition

    data, filename, error = use_case.export_bundle(novel_id)
    if error:
        raise HTTPException(400 if "Không tìm thấy" not in error else 404, error)
    assert data is not None and filename is not None
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(filename, fallback=f"novel-{novel_id}.zip")
        },
    )


@router.post("/novels/export-batch")
def export_novels_batch(
    body: BatchExportIn,
    use_case: NovelExportUseCase = Depends(get_novel_export_use_case),
):
    """Xuất hàng loạt — zip chứa từng truyện theo format."""
    from crawl.application.excel_export import content_disposition

    data, filename, error = use_case.export_batch(body.novel_ids, body.format)
    if error:
        raise HTTPException(400, error)
    assert data is not None and filename is not None
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename, fallback="export-batch.zip")},
    )


@router.post("/novels/{novel_id}/review-all", response_model=ReviewAllOut)
def review_all_chapters(
    novel_id: int,
    use_case: ReviewAllChaptersUseCase = Depends(get_review_all_use_case),
):
    """Đánh dấu đã review mọi chương đã có cleaned — không mở từng dialog."""
    result = use_case.execute(novel_id)
    if not result.success:
        code = 400 if result.error and "Không tìm thấy" not in result.error else 404
        raise HTTPException(code, result.error)
    return result


# -------------------------------------------------------------- Chapters --
# "Review chương" — crawl về mà không xem/sửa được thì vô dụng: cho phép
# đọc raw text 1 chương và lưu lại bản đã sửa (fix encoding/rác quảng cáo
# sót/lỗi chính tả...), đánh dấu đã review.

@router.get("/chapters/{chapter_id}/content", response_model=ChapterContentOut)
def get_chapter_content(
    chapter_id: int, use_case: GetChapterContentUseCase = Depends(get_chapter_content_use_case)
):
    result = use_case.execute(chapter_id)
    if not result.success:
        raise HTTPException(404, result.error)
    return result


@router.put("/chapters/{chapter_id}/content", response_model=ChapterContentOut)
def update_chapter_content(
    chapter_id: int,
    body: ChapterContentIn,
    use_case: UpdateChapterContentUseCase = Depends(get_update_chapter_content_use_case),
):
    result = use_case.execute(chapter_id, body.content)
    if not result.success:
        raise HTTPException(400, result.error)
    return result


@router.delete("/chapters/{chapter_id}/cleaned", response_model=ChapterContentOut)
def discard_chapter_cleaned(
    chapter_id: int,
    use_case: DiscardChapterCleanedUseCase = Depends(get_discard_chapter_cleaned_use_case),
):
    """Xóa bản cleaned — trở về chỉ raw (như trước làm mượt)."""
    result = use_case.execute(chapter_id)
    if not result.success:
        raise HTTPException(404, result.error)
    return result


@router.delete("/chapters/{chapter_id}", response_model=DeleteOut)
def delete_chapter(
    chapter_id: int,
    use_case: DeleteChapterUseCase = Depends(get_delete_chapter_use_case),
):
    """Xóa 1 chương + file raw/cleaned. Chặn khi novel đang crawl."""
    result = use_case.execute(chapter_id)
    if not result.success:
        status = 404 if result.error and "Không tìm thấy" in result.error else 400
        raise HTTPException(status, result.error)
    return result


@router.post("/chapters/{chapter_id}/retry", response_model=ChapterRetryOut)
def retry_chapter(
    chapter_id: int,
    use_case: RetryChapterUseCase = Depends(get_retry_chapter_use_case),
):
    """Crawl lại ĐÚNG 1 chương lỗi (mục 9.6) — KHÔNG đụng chương khác,
    không crawl lại cả truyện (khác `/novels/{id}/retry`, mục 9.2b). Chạy
    ĐỒNG BỘ (1 request mạng cho 1 chương, đủ nhanh — khác quét cả thể loại/
    truyện luôn chạy nền). 404 nếu không tìm thấy chương/truyện của nó."""
    result = use_case.execute(chapter_id)
    if not result.success and result.error in (
        "Không tìm thấy chương", "Không tìm thấy truyện của chương này",
    ):
        raise HTTPException(404, result.error)
    return result


# -------------------------------------------------------------- Settings --

@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    """Cookie phiên chỉ trả has_cookie + hint; key nội bộ (scheduler…) bị ẩn."""
    from crawl.api.settings_guard import public_settings

    return {"values": public_settings(get_all(db))}


@router.patch("/settings", response_model=SettingsOut)
def update_settings(body: SettingsPatchIn, db: Session = Depends(get_db)):
    """Chỉ nhận key đã biết (global + setting riêng từng site) với đúng kiểu
    — sai thì 422, không ghi gì. Cookie phiên sửa qua PUT /sites/{k}/session."""
    from crawl.api.settings_guard import daily_schedule_sources, public_settings, validate_settings_patch
    from platform_.scheduler import seed_last_fired_if_past

    clean, errors = validate_settings_patch(body.values)
    if errors:
        raise HTTPException(422, "Setting không hợp lệ: " + "; ".join(errors))
    for key, value in clean.items():
        set_setting(db, key, value)
    # Bật/sửa lịch hàng ngày SAU giờ hẹn hôm nay -> không quét ngay, chờ ngày mai.
    for source_key in daily_schedule_sources(list(clean)):
        try:
            seed_last_fired_if_past(db, source_key)
        except Exception:
            logger.exception("Không seed last_fired cho %s", source_key)
    return {"values": public_settings(get_all(db))}


# -------------------------------------------------------------- Dry-run --

@router.post("/dry-run", response_model=DryRunOut)
def dry_run(body: DryRunIn, use_case: DryRunUseCase = Depends(get_dry_run_use_case)):
    return use_case.execute(body.source_key, body.url, body.mode)
