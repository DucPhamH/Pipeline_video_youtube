"""Inbox vận hành — running / needs_review / ready_export."""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.domain.entities import JobStatus, SegmentStatus, VariantStatus
from translate.infrastructure.persistence.repositories import (
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)


def build_inbox(db: Session, *, limit: int = 100) -> dict:
    work_repo = WorkRepository(db)
    variant_repo = VariantRepository(db)
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)

    running: list[dict] = []
    needs_review: list[dict] = []
    ready_export: list[dict] = []

    for work in work_repo.list_all(limit=limit):
        if work.id is None:
            continue
        for variant in variant_repo.list_by_work(work.id):
            if variant.id is None:
                continue
            latest = job_repo.latest_for_variant(variant.id)
            item = {
                "work_id": work.id,
                "work_title": work.title,
                "variant_id": variant.id,
                "mode": variant.mode,
                "variant_status": variant.status.value,
                "job_id": latest.id if latest else None,
                "job_status": latest.status.value if latest else None,
            }
            if latest and latest.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                running.append(item)
                continue
            if variant.status == VariantStatus.READY and latest and latest.status == JobStatus.COMPLETED:
                segs = seg_repo.list_by_job(latest.id)  # type: ignore[arg-type]
                done = [
                    s
                    for s in segs
                    if s.status in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE)
                ]
                unreviewed = sum(1 for s in done if not s.reviewed)
                item["unreviewed"] = unreviewed
                if unreviewed > 0:
                    needs_review.append(item)
                else:
                    ready_export.append(item)

    return {
        "running": running,
        "needs_review": needs_review,
        "ready_export": ready_export,
    }
