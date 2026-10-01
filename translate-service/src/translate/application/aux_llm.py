"""Chọn AI cho lệnh gọi phụ ngoài job (bảng duyệt tên, bảng đổi vỏ)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.application.run_job import aux_chat_config, resolve_provider_config
from translate.infrastructure.ai_registry import load_ai_provider
from translate.infrastructure.persistence.models import JobModel
from translate.infrastructure.persistence.repositories import (
    JobRepository,
    VariantRepository,
)


def resolve_work_ai_config(db: Session, *, work_id: int, provider_id: int | None = None) -> dict:
    """provider_id (AI đã lưu) > AI của job gần nhất thuộc Work. Không có / chỉ
    là mock → ValueError (router trả 400)."""
    if provider_id is not None:
        cfg = resolve_provider_config(db, ai_provider_id=provider_id)
    else:
        variant_ids = [v.id for v in VariantRepository(db).list_by_work(work_id)]
        row = (
            db.query(JobModel.id)
            .filter(JobModel.variant_id.in_(variant_ids))
            .order_by(JobModel.id.desc())
            .first()
            if variant_ids
            else None
        )
        if row is None:
            raise ValueError("Work chưa có job nào — chọn provider_id (AI đã lưu)")
        job = JobRepository(db).get(row[0])
        assert job is not None
        if job.ai_provider_id is not None and load_ai_provider(db, job.ai_provider_id):
            cfg = resolve_provider_config(db, ai_provider_id=job.ai_provider_id, model=job.model or None)
        else:
            cfg = {
                "provider": job.provider,
                "model": job.model,
                "base_url": job.base_url,
                "api_key": job.api_key,
                "requires_api_key": job.requires_api_key,
            }
            if job.provider != "mock" and job.requires_api_key and not (job.api_key or "").strip():
                cfg["provider"] = "mock"
    if str(cfg.get("provider") or "mock") == "mock":
        raise ValueError("AI mock không trích/đề xuất tên được — chọn AI thật (provider_id)")
    return cfg


def make_chat(cfg: dict):
    """(system, user) -> raw — dùng cho skin_map.generate_skin_map / trích tên."""
    return lambda system, user: aux_chat_config(cfg, system=system, user=user)
