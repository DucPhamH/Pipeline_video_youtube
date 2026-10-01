"""Gửi novel đã crawl sang translate-service (HTTP, không share DB)."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from crawl.application.fingerprint import content_fingerprint
from crawl.application.use_cases import RawTextStorage
from crawl.domain.entities import ChapterStatus, DomainError, Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from crawl.infrastructure.sources.registry import SOURCES
from platform_.config import config


@dataclass
class SendToTranslateResult:
    novel: Novel
    work_id: int
    variant_id: int
    job_id: int | None
    missing_cleaned: int
    unreviewed: int
    created: bool
    # Work đã tạo nhưng start job lỗi — novel VẪN đánh dấu translating (đã
    # handoff); caller báo lỗi rõ kèm work_id để chạy lại job bên translate.
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def service_auth_headers() -> dict[str, str]:
    """Header token khi gọi service khác (FOLIO_API_TOKEN dùng chung)."""
    token = (config.folio_api_token or "").strip()
    return {"X-Folio-Token": token} if token else {}


def _handoff_warnings(db: Session, novel: Novel) -> list[str]:
    warnings: list[str] = []
    if novel.lifecycle_status == NovelLifecycle.ERROR:
        warnings.append(f"Truyện đang ở trạng thái lỗi: {novel.error_message or 'không rõ'}")
    elif novel.error_message:
        warnings.append(novel.error_message)
    counts = SqlAlchemyChapterRepository(db).count_status_by_novels([novel.id]).get(novel.id, {})
    failed = counts.get(ChapterStatus.FAILED.value, 0)
    if failed:
        warnings.append(f"Còn {failed} chương lỗi (failed) — bản dịch sẽ thiếu các chương này")
    return warnings


def _build_handoff_payload(db: Session, novel: Novel, *, prefer_cleaned: bool = True) -> dict:
    source = SOURCES.get(novel.source_key)
    cfg = getattr(source, "cfg", None) if source is not None else None
    lang_src = getattr(cfg, "content_locale", "zh") if cfg else "zh"

    storage = RawTextStorage(config.raw_dir)
    chapter_repo = SqlAlchemyChapterRepository(db)
    chapters = chapter_repo.list_by_novel_filtered(
        novel.id,  # type: ignore[arg-type]
        status=ChapterStatus.CRAWLED.value,
        limit=None,
        offset=0,
    )
    out_chapters: list[dict] = []
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
            {
                "index": ch.chapter_index,
                # Thứ tự đọc (vị trí TOC) — index giữ làm định danh ổn định.
                "order": ch.sort_key[0],
                "title": ch.title,
                "text": text,
                "fingerprint": content_fingerprint(text),
                "has_cleaned": has_cleaned,
                "reviewed": bool(ch.reviewed),
                "crawl_chapter_id": ch.id,
            }
        )

    if not out_chapters:
        raise ValueError("Truyện chưa có chương crawled nào để handoff")

    base = (config.crawl_public_url or "").rstrip("/")
    callback_url = f"{base}/api/crawl/novels/{novel.id}/translate-lifecycle"

    return {
        "external_id": f"crawl:novel:{novel.id}",
        "title": novel.title,
        "author": novel.author or "",
        "lang_src": lang_src,
        "lang_tgt_hint": "vi",
        "source_key": novel.source_key,
        "source_url": novel.source_url,
        "chapters": out_chapters,
        "missing_cleaned": missing_cleaned,
        "unreviewed": unreviewed,
        "callback_url": callback_url,
    }


def send_to_translate(
    db: Session,
    *,
    novel_id: int,
    require_cleaned: bool = True,
    start_job: bool = True,
) -> SendToTranslateResult:
    novel_repo = SqlAlchemyNovelRepository(db)
    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise LookupError("Không tìm thấy truyện")

    if novel.lifecycle_status not in (
        NovelLifecycle.FULLY_CRAWLED,
        NovelLifecycle.ERROR,
        NovelLifecycle.TRANSLATING,
        NovelLifecycle.READY_FOR_VIDEO,
    ):
        raise ValueError(
            f"Không thể gửi dịch novel đang ở trạng thái {novel.lifecycle_status.value}"
        )

    payload = _build_handoff_payload(db, novel)
    missing = int(payload["missing_cleaned"])
    unreviewed = int(payload["unreviewed"])
    if require_cleaned and missing > 0:
        raise ValueError(
            f"Còn {missing} chương chưa làm mượt (cleaned) — chạy Smooth hoặc gửi với require_cleaned=false"
        )

    base = (config.translate_service_url or "").rstrip("/")
    if not base:
        raise ValueError("TRANSLATE_SERVICE_URL chưa cấu hình")

    warnings = _handoff_warnings(db, novel)
    job_id: int | None = None
    job_error: str | None = None
    try:
        with httpx.Client(timeout=120.0, headers=service_auth_headers()) as client:
            r = client.post(f"{base}/api/translate/works/from-crawl", json=payload)
            if r.status_code >= 400:
                raise ValueError(f"translate from-crawl: {r.status_code} {r.text[:300]}")
            work = r.json()
            work_id = int(work["id"])
            variants = work.get("variants") or []
            if not variants:
                raise ValueError("translate không trả variant")
            variant_id = int(variants[0]["id"])
            created = bool(work.get("external_id"))
            if start_job:
                # Work ĐÃ tạo bên translate — lỗi từ đây không được làm mất
                # dấu handoff (novel vẫn chuyển translating, báo lỗi job rõ).
                try:
                    jr = client.post(f"{base}/api/translate/variants/{variant_id}/jobs")
                    if jr.status_code >= 400:
                        job_error = f"{jr.status_code} {jr.text[:300]}"
                    else:
                        job_id = int(jr.json()["id"])
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    job_error = str(exc)
    except httpx.HTTPError as exc:
        raise ValueError(f"Không kết nối translate-service ({base}): {exc}") from exc

    if novel.lifecycle_status != NovelLifecycle.TRANSLATING:
        try:
            novel.mark_translating()
        except DomainError as exc:
            raise ValueError(str(exc)) from exc
        novel_repo.update(novel)
        db.commit()

    error = None
    if job_error:
        error = (
            f"Đã gửi truyện sang dịch (Work #{work_id}) nhưng không start được job dịch: "
            f"{job_error} — mở /translate/{work_id} để chạy lại job"
        )

    return SendToTranslateResult(
        novel=novel,
        work_id=work_id,
        variant_id=variant_id,
        job_id=job_id,
        missing_cleaned=missing,
        unreviewed=unreviewed,
        created=created,
        error=error,
        warnings=warnings,
    )


def apply_translate_lifecycle(
    db: Session,
    *,
    novel_id: int,
    status: str,
    message: str | None = None,
) -> Novel:
    novel_repo = SqlAlchemyNovelRepository(db)
    novel = novel_repo.get_by_id(novel_id)
    if novel is None:
        raise LookupError("Không tìm thấy truyện")

    st = (status or "").strip().lower()
    try:
        if st == NovelLifecycle.TRANSLATING.value:
            novel.mark_translating()
        elif st == NovelLifecycle.READY_FOR_VIDEO.value:
            novel.mark_ready_for_video()
        elif st in ("failed", "error"):
            novel.mark_translate_failed(message or "Dịch thất bại")
        else:
            raise ValueError(
                f"status không hợp lệ: {status} "
                f"(translating | ready_for_video | failed)"
            )
    except DomainError as exc:
        raise ValueError(str(exc)) from exc

    novel_repo.update(novel)
    db.commit()
    return novel
