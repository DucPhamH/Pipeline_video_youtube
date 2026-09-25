"""Gửi novel đã crawl sang translate-service (HTTP, không share DB)."""
from __future__ import annotations

from dataclasses import dataclass

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
    error: str | None = None


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

    try:
        with httpx.Client(timeout=120.0) as client:
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
            job_id: int | None = None
            if start_job:
                jr = client.post(f"{base}/api/translate/variants/{variant_id}/jobs")
                if jr.status_code >= 400:
                    raise ValueError(f"translate start job: {jr.status_code} {jr.text[:300]}")
                job_id = int(jr.json()["id"])
    except httpx.HTTPError as exc:
        raise ValueError(f"Không kết nối translate-service ({base}): {exc}") from exc

    try:
        novel.mark_translating()
    except DomainError as exc:
        raise ValueError(str(exc)) from exc
    novel_repo.update(novel)
    db.commit()

    return SendToTranslateResult(
        novel=novel,
        work_id=work_id,
        variant_id=variant_id,
        job_id=job_id,
        missing_cleaned=missing,
        unreviewed=unreviewed,
        created=created,
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
