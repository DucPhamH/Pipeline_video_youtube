"""Một nút: làm mượt chương đã cào, gửi dịch, khi bản dịch xong thì tạo audio.

Callback từ translate chỉ được nối tiếp khi stage đã là translating — callback
của một job cũ (lúc stage còn smoothing) không được tạo audio nhầm.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading

import httpx
from sqlalchemy.orm import Session

from crawl.application.send_to_translate import send_to_translate, service_auth_headers
from crawl.domain.entities import NovelLifecycle
from crawl.infrastructure.persistence.models import NovelPipelineModel
from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository
from platform_.config import config
from platform_.db import SessionLocal
from platform_.locks import release, try_acquire

logger = logging.getLogger("crawl.pipeline")

PRESETS = ("nu_ke_cham", "nam_ke", "doi_thoai")
ENGINES = ("edge", "mock")
_STARTABLE = (
    NovelLifecycle.FULLY_CRAWLED,
    NovelLifecycle.ERROR,
    NovelLifecycle.TRANSLATING,
    NovelLifecycle.READY_FOR_VIDEO,
)
_OPEN = ("smoothing", "translating", "speaking")


class PipelineBusy(Exception):
    pass


def begin(db: Session, novel_id: int, *, voice_preset: str, engine: str) -> NovelPipelineModel:
    preset = (voice_preset or "nam_ke").strip()
    engine_name = (engine or "edge").strip().lower()
    if preset not in PRESETS:
        raise ValueError("Preset giọng không hợp lệ")
    if engine_name not in ENGINES:
        raise ValueError("Engine phải là edge hoặc mock")
    novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
    if novel is None:
        raise LookupError("Không tìm thấy truyện")
    if novel.lifecycle_status not in _STARTABLE:
        raise ValueError(f"Chưa cào xong (hiện: {novel.lifecycle_status.value})")
    row = db.get(NovelPipelineModel, novel_id)
    if row is not None and row.stage in _OPEN:
        raise PipelineBusy()
    if row is None:
        row = NovelPipelineModel(novel_id=novel_id)
    row.stage = "smoothing"
    row.voice_preset = preset
    row.engine = engine_name
    row.error = None
    row.translate_work_id = None
    row.translate_variant_id = None
    row.tts_work_id = None
    row.updated_at = dt.datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def smooth_novel(db: Session, novel_id: int):
    from crawl.application.use_cases import RawTextStorage, SmoothNovelUseCase
    from crawl.infrastructure.persistence.repositories import (
        SqlAlchemyChapterRepository,
        SqlAlchemyNovelRepository,
    )
    from platform_.settings_store import get_per_site_setting

    return SmoothNovelUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(config.raw_dir),
        get_opencc_mode=lambda sk: get_per_site_setting(db, "opencc_mode", sk) or "none",
    ).execute(novel_id)


def _fail(db: Session, novel_id: int, message: str) -> None:
    db.rollback()
    row = db.get(NovelPipelineModel, novel_id)
    if row is None or row.stage not in ("smoothing", "translating"):
        return
    row.stage = "error"
    row.error = message[:500]
    db.commit()


def execute(db: Session, novel_id: int) -> None:
    """Làm mượt rồi gửi dịch. Audio chờ callback ready_for_video."""
    if db.get(NovelPipelineModel, novel_id) is None:
        return
    try:
        smoothed = smooth_novel(db, novel_id)
        if not smoothed.success:
            _fail(db, novel_id, smoothed.error or "Không làm mượt được")
            return
        sent = send_to_translate(db, novel_id=novel_id, require_cleaned=False, start_job=True)
    except (ValueError, LookupError) as exc:
        _fail(db, novel_id, str(exc))
        return
    row = db.get(NovelPipelineModel, novel_id)
    if row is None:
        return
    row.translate_work_id = sent.work_id
    row.translate_variant_id = sent.variant_id
    if sent.error and row.stage in ("smoothing", "translating"):
        row.stage = "error"
        row.error = sent.error[:500]
        db.commit()
        return
    if row.stage == "smoothing":
        row.stage = "translating"
    db.commit()
    novel = SqlAlchemyNovelRepository(db).get_by_id(novel_id)
    if novel is not None and novel.lifecycle_status == NovelLifecycle.READY_FOR_VIDEO:
        on_translate_status(db, novel_id, "ready_for_video")


def on_translate_status(
    db: Session, novel_id: int, status: str, message: str | None = None, *, spawn: bool = True
) -> None:
    row = db.get(NovelPipelineModel, novel_id)
    if row is None or row.stage != "translating":
        return
    st = (status or "").strip().lower()
    if st in ("failed", "error"):
        row.stage = "error"
        row.error = (message or "Dịch thất bại")[:500]
        db.commit()
        return
    if st != "ready_for_video":
        return
    if not try_acquire(f"pipeline-audio:{novel_id}"):
        return
    row.stage = "speaking"
    db.commit()
    if spawn:
        threading.Thread(
            target=_handoff_thread, args=(novel_id,), daemon=True, name=f"pipeline-audio-{novel_id}"
        ).start()
        return
    try:
        handoff(db, novel_id)
    finally:
        release(f"pipeline-audio:{novel_id}")


def _handoff_thread(novel_id: int) -> None:
    db = SessionLocal()
    try:
        handoff(db, novel_id)
    except Exception:
        logger.exception("Lỗi khi tạo audio cho novel %s", novel_id)
        _fail_speaking(db, novel_id, "Lỗi không mong đợi khi tạo audio")
    finally:
        db.close()
        release(f"pipeline-audio:{novel_id}")


def _fail_speaking(db: Session, novel_id: int, message: str) -> None:
    db.rollback()
    row = db.get(NovelPipelineModel, novel_id)
    if row is None or row.stage != "speaking":
        return
    row.stage = "error"
    row.error = message[:500]
    db.commit()


def handoff(db: Session, novel_id: int) -> None:
    row = db.get(NovelPipelineModel, novel_id)
    if row is None or row.stage != "speaking":
        return
    preset = row.voice_preset
    engine = row.engine
    variant_id = row.translate_variant_id
    try:
        if not variant_id:
            variant_id = _find_variant(novel_id)
        work_id = start_listen(variant_id, preset=preset, engine=engine)
    except Exception as exc:  # noqa: BLE001 — ghi lỗi lên pipeline, không làm hỏng callback
        _fail_speaking(db, novel_id, str(exc))
        return
    row = db.get(NovelPipelineModel, novel_id)
    if row is not None and row.stage == "speaking":
        row.stage = "done"
        row.tts_work_id = work_id
        row.translate_variant_id = variant_id
        row.error = None
        db.commit()


def start_listen(variant_id: int, *, preset: str, engine: str) -> int:
    """Lấy bản dịch đã xong và bắt đầu đọc. Sách nghe đã có thì được cập nhật chữ."""
    book = _fetch_book(variant_id)
    chapters = [
        {"index": int(c["index"]), "title": c.get("title") or "", "text": (c.get("text") or "").strip()}
        for c in book.get("chapters") or []
        if (c.get("text") or "").strip()
    ]
    if not chapters:
        raise ValueError("Bản dịch chưa có chương để đọc")
    return _start_tts(
        title=book.get("title") or "",
        author=book.get("author") or "",
        lang=book.get("lang_tgt") or "vi",
        external_id=f"translate:variant:{variant_id}",
        chapters=chapters,
        engine=engine,
        preset=preset,
    )


def _fetch_book(variant_id: int) -> dict:
    base = (config.translate_service_url or "").rstrip("/")
    resp = httpx.get(
        f"{base}/api/translate/variants/{variant_id}/export.json",
        headers=service_auth_headers(),
        timeout=120,
    )
    if resp.status_code >= 400:
        raise ValueError(f"Không lấy được bản dịch ({resp.status_code})")
    return resp.json()


def _find_variant(novel_id: int) -> int:
    base = (config.translate_service_url or "").rstrip("/")
    resp = httpx.get(f"{base}/api/translate/works", headers=service_auth_headers(), timeout=30)
    if resp.status_code >= 400:
        raise ValueError(f"Không đọc được danh sách bản dịch ({resp.status_code})")
    external = f"crawl:novel:{novel_id}"
    for work in resp.json().get("items") or []:
        if work.get("external_id") != external:
            continue
        variants = work.get("variants") or []
        if variants:
            return int(variants[0]["id"])
    raise ValueError("Không tìm thấy bản dịch của truyện này")


def _start_tts(
    *,
    title: str,
    author: str,
    lang: str,
    external_id: str,
    chapters: list[dict],
    engine: str,
    preset: str,
) -> int:
    base = (config.tts_service_url or "").rstrip("/")
    if not base:
        raise ValueError("TTS_SERVICE_URL chưa cấu hình")
    with httpx.Client(timeout=120, headers=service_auth_headers()) as client:
        created = client.post(
            f"{base}/api/tts/works/from-translate",
            json={
                "title": title,
                "author": author,
                "lang": lang,
                "external_id": external_id,
                "chapters": chapters,
            },
        )
        if created.status_code >= 400:
            raise ValueError(f"Không tạo được sách nghe ({created.status_code})")
        work_id = int(created.json()["id"])
        started = client.post(
            f"{base}/api/tts/works/{work_id}/readings",
            json={"engine": engine, "preset_id": preset},
        )
        if started.status_code >= 400:
            raise ValueError(f"Không bắt đầu đọc được ({started.status_code}) {started.text[:200]}")
    return work_id
