"""Tạo / clone Variant.

Quy tắc chi phí (spec mục 4.3): mọi variant mode != full luôn fork từ variant
`full` cùng Work/lang_tgt — không dịch lại từ nguồn. `_resolve_full_source`
tìm variant full sẵn có, hoặc tạo (rỗng, chưa chạy) nếu Work chưa có, rồi gắn
`source_variant_id` — bất kể tạo qua create_variant hay clone_variant.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.application.modes import normalize_mode_params, validate_mode
from translate.domain.entities import Variant, VariantStatus
from translate.infrastructure.persistence.repositories import VariantRepository, WorkRepository


def _resolve_full_source(db: Session, *, work_id: int, lang_tgt: str) -> int:
    repo = VariantRepository(db)
    existing = [
        v for v in repo.list_by_work(work_id) if v.mode == "full" and v.lang_tgt == lang_tgt
    ]
    if existing:
        return min(v.id for v in existing)  # type: ignore[return-value]
    full = repo.add(
        Variant(
            id=None,
            work_id=work_id,
            mode="full",
            status=VariantStatus.PENDING,
            lang_tgt=lang_tgt,
            mode_params={},
        )
    )
    return full.id  # type: ignore[return-value]


def create_variant(
    db: Session,
    *,
    work_id: int,
    mode: str,
    mode_params: dict | None = None,
    lang_tgt: str | None = None,
) -> Variant:
    work = WorkRepository(db).get(work_id)
    if work is None:
        raise LookupError(f"Work {work_id} không tồn tại")
    mode = validate_mode(mode)
    params = normalize_mode_params(mode, mode_params)
    resolved_lang_tgt = lang_tgt or work.lang_tgt or "vi"
    source_variant_id = (
        _resolve_full_source(db, work_id=work_id, lang_tgt=resolved_lang_tgt)
        if mode != "full"
        else None
    )
    variant = VariantRepository(db).add(
        Variant(
            id=None,
            work_id=work_id,
            mode=mode,
            status=VariantStatus.PENDING,
            lang_tgt=resolved_lang_tgt,
            mode_params=params,
            source_variant_id=source_variant_id,
        )
    )
    db.commit()
    return variant


def clone_variant(
    db: Session,
    *,
    variant_id: int,
    mode: str | None = None,
    mode_params: dict | None = None,
    lang_tgt: str | None = None,
) -> Variant:
    repo = VariantRepository(db)
    src = repo.get(variant_id)
    if src is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")
    new_mode = validate_mode(mode or src.mode)
    # Nếu đổi mode và không truyền params → mặc định mode mới; nếu cùng mode và không truyền → copy
    if mode_params is not None:
        params = normalize_mode_params(new_mode, mode_params)
    elif mode and mode != src.mode:
        params = normalize_mode_params(new_mode, None)
    else:
        params = normalize_mode_params(new_mode, src.mode_params)
    resolved_lang_tgt = lang_tgt or src.lang_tgt
    source_variant_id = (
        _resolve_full_source(db, work_id=src.work_id, lang_tgt=resolved_lang_tgt)
        if new_mode != "full"
        else None
    )
    variant = repo.add(
        Variant(
            id=None,
            work_id=src.work_id,
            mode=new_mode,
            status=VariantStatus.PENDING,
            lang_tgt=resolved_lang_tgt,
            mode_params=params,
            source_variant_id=source_variant_id,
        )
    )
    db.commit()
    return variant
