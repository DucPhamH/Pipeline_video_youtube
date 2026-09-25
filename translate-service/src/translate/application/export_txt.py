"""Export bản dịch TXT từ Variant (segment mới nhất completed)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.domain.entities import JobStatus, SegmentStatus
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)
from translate.infrastructure.persistence.models import JobModel


def export_variant_txt(db: Session, *, variant_id: int) -> bytes:
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

    # Job completed gần nhất
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

    parts: list[str] = [work.title.strip() or "untitled"]
    if work.author:
        parts.append(f"Author: {work.author}")
    parts.append(f"lang: {work.lang_src} → {variant.lang_tgt}")
    parts.append("")
    parts.append("=" * 40)
    parts.append("")

    for seg in segments:
        if seg.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue
        ch = chapters.get(seg.chapter_index)
        title = (ch.title if ch else "") or f"Chapter {seg.chapter_index}"
        body = (seg.output_text or "").strip()
        parts.append(title)
        parts.append("-" * min(40, max(8, len(title))))
        parts.append(body)
        parts.append("")
        parts.append("")

    text = "\n".join(parts).rstrip() + "\n"
    return text.encode("utf-8")
