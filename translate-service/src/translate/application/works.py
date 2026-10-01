"""Xóa Work — cascade chapters/variants/jobs/segments (ORM), dọn glossary thủ công
(glossary_terms không có ORM relationship từ Work nên không tự cascade)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.domain.entities import JobStatus
from translate.infrastructure.persistence.repositories import (
    GlossaryRepository,
    JobRepository,
    NameApplyBatchRepository,
    SkinMapRepository,
    VariantRepository,
    WorkRepository,
)


def delete_work(db: Session, *, work_id: int) -> None:
    work_repo = WorkRepository(db)
    work = work_repo.get(work_id)
    if work is None:
        raise LookupError(f"Work {work_id} không tồn tại")

    variant_repo = VariantRepository(db)
    job_repo = JobRepository(db)
    for v in variant_repo.list_by_work(work_id):
        latest = job_repo.latest_for_variant(v.id)  # type: ignore[arg-type]
        if latest is not None and latest.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise ValueError(
                f"Variant #{v.id} đang chạy job — dừng/tạm dừng trước khi xóa Work"
            )

    glossary_repo = GlossaryRepository(db)
    for term in glossary_repo.list_by_work(work_id):
        glossary_repo.delete(term.id)  # type: ignore[arg-type]
    # Bảng đổi vỏ + lô áp tên không có relationship ORM — dọn tay như glossary.
    skin_repo = SkinMapRepository(db)
    for v in variant_repo.list_by_work(work_id):
        skin_repo.delete_by_variant(v.id)  # type: ignore[arg-type]
    NameApplyBatchRepository(db).delete_by_work(work_id)

    work_repo.delete(work_id)
    db.commit()
