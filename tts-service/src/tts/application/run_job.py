"""Chạy job đọc trong thread của process API."""
from __future__ import annotations

import json
import logging
import threading

from platform_.db import SessionLocal
from tts.application.cast import tag_chapter, voices_for_pieces
from tts.application.speak import SpeakParams, absolute_audio, relative_audio, render
from tts.infrastructure.persistence.models import CastMemberModel, JobModel, ReadingModel, SegmentModel

log = logging.getLogger(__name__)

_DONE = ("done", "skipped_cache")
# Chương không có chữ: không đọc, không tính là lỗi.
_SKIPPED = "skipped"
_INTERRUPTED = "Dịch vụ khởi động lại khi đang đọc — bấm đọc tiếp"


# Huỷ rồi đọc tiếp nhanh: thread cũ có thể còn kẹt trong engine; lúc nó xong chương,
# status DB đã về queued/running nên nó không tự thấy mình bị dừng → 2 thread cùng đọc.
# Mỗi lần launch tăng generation; thread nào thấy generation của mình cũ thì thoát.
_run_generation: dict[int, int] = {}
_run_generation_guard = threading.Lock()


def _next_generation(job_id: int) -> int:
    with _run_generation_guard:
        gen = _run_generation.get(job_id, 0) + 1
        _run_generation[job_id] = gen
        return gen


def _is_stale_run(job_id: int, generation: int | None) -> bool:
    if generation is None:
        return False
    with _run_generation_guard:
        return _run_generation.get(job_id) != generation


def launch(job_id: int) -> None:
    generation = _next_generation(job_id)
    threading.Thread(
        target=run_job, args=(job_id,), kwargs={"generation": generation}, daemon=True
    ).start()


def run_job(job_id: int, generation: int | None = None) -> None:
    db = SessionLocal()
    try:
        _run(db, job_id, generation)
    except Exception as exc:  # noqa: BLE001 — không để job treo ở running
        log.exception("tts job %s crashed", job_id)
        if not _is_stale_run(job_id, generation):
            _mark_crashed(db, job_id, exc)
    finally:
        db.close()


def _mark_crashed(db, job_id: int, exc: Exception) -> None:
    try:
        db.rollback()
        job = db.get(JobModel, job_id)
        if job is None:
            return
        if job.status != "cancelled":
            job.status = "failed"
            job.error = (f"Lỗi job: {exc}")[:500]
        reading = db.get(ReadingModel, job.reading_id)
        if reading is not None and reading.status in ("queued", "running"):
            reading.status = "cancelled" if job.status == "cancelled" else "failed"
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("không đánh dấu được job %s lỗi", job_id)
        db.rollback()


def recover_interrupted() -> int:
    """Lúc khởi động: job queued/running không còn thread nào chạy → failed để bấm đọc tiếp."""
    db = SessionLocal()
    try:
        jobs = db.query(JobModel).filter(JobModel.status.in_(("queued", "running"))).all()
        for job in jobs:
            job.status = "failed"
            job.error = _INTERRUPTED
            reading = db.get(ReadingModel, job.reading_id)
            if reading is not None and reading.status in ("queued", "running"):
                reading.status = "failed"
        db.commit()
        return len(jobs)
    finally:
        db.close()


def _run(db, job_id: int, generation: int | None = None) -> None:
    job = db.get(JobModel, job_id)
    if job is None or job.status == "cancelled" or _is_stale_run(job_id, generation):
        return
    job.status = "running"
    job.error = None
    reading = db.get(ReadingModel, job.reading_id)
    if reading is not None:
        reading.status = "running"
    db.commit()

    params = SpeakParams(
        engine=job.engine,
        voice=job.voice,
        dialogue_voice=job.dialogue_voice or "",
        rate=job.rate,
        pitch=job.pitch,
        volume=job.volume,
        style=job.style or "",
        male_voice=job.male_voice or "",
        female_voice=job.female_voice or "",
        device=job.device or "cpu",
    )
    cast_rows: list[dict] = []
    if job.use_cast and reading is not None:
        members = (
            db.query(CastMemberModel)
            .filter(CastMemberModel.work_id == reading.work_id)
            .order_by(CastMemberModel.id)
            .all()
        )
        cast_rows = [{"name": m.name, "gender": m.gender, "voice": m.voice or ""} for m in members]
    segments = (
        db.query(SegmentModel)
        .filter(SegmentModel.job_id == job_id)
        .order_by(SegmentModel.chapter_index)
        .all()
    )
    for seg in segments:
        if _is_stale_run(job_id, generation):
            return  # đã có thread mới cho job này — để nó ghi kết quả
        db.refresh(job)
        if job.status == "cancelled":
            break
        if seg.status in _DONE or seg.status == _SKIPPED:
            continue
        if not _speakable(seg.source_text):
            seg.status = _SKIPPED
            seg.error = None
            db.commit()
            continue
        try:
            voiced = None
            if job.use_cast:
                pieces = json.loads(seg.pieces_json) if seg.pieces_json else None
                if not pieces:
                    if not job.provider_id:
                        raise RuntimeError("Thiếu AI để gắn câu thoại")
                    pieces = tag_chapter(seg.source_text, cast_rows, job.provider_id)
                    seg.pieces_json = json.dumps(pieces, ensure_ascii=False)
                    db.commit()
                voiced = voices_for_pieces(pieces, cast_rows, params)
            path, key, cached = render(seg.source_text, params, voiced)
            seg.cache_key = key
            seg.audio_path = relative_audio(path)
            seg.status = "skipped_cache" if cached else "done"
            seg.error = None
        except Exception as exc:  # noqa: BLE001 — một chương lỗi không dừng cả sách
            seg.status = "failed"
            seg.error = str(exc)[:500]
        if _is_stale_run(job_id, generation):
            # Chương vừa đọc vẫn hợp lệ (cache theo key), nhưng thread mới có thể đã đặt lại
            # segment này → không ghi đè trạng thái.
            db.rollback()
            return
        db.commit()

    if _is_stale_run(job_id, generation):
        return
    db.refresh(job)
    if job.status == "cancelled":
        final = "cancelled"
    elif any(s.status == "failed" for s in segments):
        final = "failed"
        job.error = "Một hoặc nhiều chương lỗi"
    else:
        final = "completed"
        job.error = None
    job.status = final
    if reading is not None:
        reading.status = {"completed": "ready", "failed": "failed", "cancelled": "cancelled"}.get(
            final, final
        )
    db.commit()


def _speakable(text: str | None) -> bool:
    """Chương chỉ có khoảng trắng / dấu câu (vd. "* * *") thì engine không đọc được gì."""
    return any(ch.isalnum() for ch in (text or ""))


def resume_job(db, job: JobModel) -> JobModel:
    if job.status in ("queued", "running"):
        raise ValueError("Job đang chạy")
    if job.status == "completed":
        raise ValueError("Job đã xong")
    failed = [s for s in job.segments if s.status == "failed"]
    pending = [s for s in job.segments if s.status == "pending"]
    if not failed and not pending:
        raise ValueError("Không còn chương để đọc lại")
    for seg in failed:
        seg.status = "pending"
        seg.error = None
    job.status = "queued"
    job.error = None
    db.commit()
    launch(job.id)
    db.refresh(job)
    return job


def audio_file(seg: SegmentModel):
    if not seg.audio_path:
        raise LookupError("Chưa có audio")
    path = absolute_audio(seg.audio_path)
    if not path.is_file():
        raise LookupError("File audio không còn")
    return path
