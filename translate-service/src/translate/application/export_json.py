"""Export Variant dạng JSON TTS-ready."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from translate.domain.entities import JobStatus, SegmentStatus
from translate.infrastructure.persistence.models import JobModel
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)


def export_variant_json(db: Session, *, variant_id: int) -> bytes:
    variant_repo = VariantRepository(db)
    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)

    variant = variant_repo.get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")

    work = work_repo.get(variant.work_id)
    if work is None:
        raise LookupError("Work missing")

    row = (
        db.query(JobModel)
        .filter(JobModel.variant_id == variant_id, JobModel.status == JobStatus.COMPLETED.value)
        .order_by(JobModel.id.desc())
        .first()
    )
    if row is None:
        raise LookupError("Chưa có job completed để export")

    job = job_repo.get(row.id)
    assert job is not None
    segments = seg_repo.list_by_job(job.id)  # type: ignore[arg-type]
    chapters = {c.index: c for c in chapter_repo.list_by_work(work.id)}  # type: ignore[arg-type]

    items: list[dict] = []
    for seg in segments:
        if seg.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue
        ch = chapters.get(seg.chapter_index)
        text = (seg.output_text or "").strip()
        items.append(
            {
                "index": seg.chapter_index,
                "title": (ch.title if ch else "") or f"Chapter {seg.chapter_index}",
                "text": text,
                "char_count": len(text),
                "fingerprint": (ch.fingerprint if ch else "") or "",
                "reviewed": seg.reviewed,
            }
        )

    payload = {
        "format": "tts_ready_v1",
        "work_id": work.id,
        "variant_id": variant.id,
        "title": work.title,
        "author": work.author,
        "lang_src": work.lang_src,
        "lang_tgt": variant.lang_tgt,
        "mode": variant.mode,
        "mode_params": variant.mode_params or {},
        "external_id": work.external_id,
        "chapters": items,
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
