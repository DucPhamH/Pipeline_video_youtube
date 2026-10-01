"""Bảng đổi vỏ (mode reskin) — mỗi variant reskin 1 bảng `original → replacement`.

`original` là tên/thuật ngữ như trong bản FULL (glossary target_term), vì
reskin fork từ bản full đã dịch. Lúc chạy job, bảng được gắn vào mode_params
(khoá `SKIN_MAP_PARAM`, không lưu DB) để vừa vào prompt vừa vào cache key.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from translate.application.llm_json import parse_json_array
from translate.application.modes import SKIN_MAP_PARAM, build_skin_map_generate_prompt
from translate.domain.entities import GLOSSARY_KINDS, SegmentStatus, SkinMapEntry, Variant
from translate.infrastructure.persistence.repositories import (
    GlossaryRepository,
    JobRepository,
    SegmentRepository,
    SkinMapRepository,
    VariantRepository,
)

ChatFn = Callable[[str, str], str]  # (system, user) -> raw text

_MAX_ROWS = 200
_EXCERPT_CHARS = 3000


def require_reskin_variant(db: Session, variant_id: int) -> Variant:
    variant = VariantRepository(db).get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")
    if variant.mode != "reskin":
        raise ValueError("Chỉ variant reskin mới có bảng đổi vỏ")
    return variant


def skin_map_pairs(db: Session, variant_id: int) -> list[list[str]]:
    """[[original, replacement], ...] theo id — ổn định cho hash cache."""
    return [
        [e.original, e.replacement]
        for e in SkinMapRepository(db).list_by_variant(variant_id)
        if e.original.strip() and e.replacement.strip()
    ]


def effective_mode_params(db: Session, variant: Variant) -> dict:
    """mode_params dùng cho prompt + cache key: reskin thì kèm bảng đổi vỏ hiện tại."""
    params = {k: v for k, v in (variant.mode_params or {}).items() if k != SKIN_MAP_PARAM}
    if variant.mode == "reskin" and variant.id is not None:
        pairs = skin_map_pairs(db, variant.id)
        if pairs:
            params[SKIN_MAP_PARAM] = pairs
    return params


def normalize_kind(kind: str | None) -> str:
    k = (kind or "").strip().lower()
    if k not in GLOSSARY_KINDS:
        raise ValueError(f"kind không hợp lệ: {kind} (character|place|term|other)")
    return k


def _full_excerpt(db: Session, variant: Variant) -> str:
    if variant.source_variant_id is None:
        return ""
    job = JobRepository(db).latest_output_job_for_variant(variant.source_variant_id)
    if job is None:
        return ""
    parts: list[str] = []
    total = 0
    for seg in SegmentRepository(db).list_by_job(job.id):  # type: ignore[arg-type]
        if seg.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE) or not seg.output_text:
            continue
        chunk = seg.output_text[:1500]
        parts.append(chunk)
        total += len(chunk)
        if total >= _EXCERPT_CHARS:
            break
    return "\n\n".join(parts)[:_EXCERPT_CHARS]


def generate_skin_map(
    db: Session, *, variant: Variant, chat: ChatFn, overwrite: bool = False
) -> list[SkinMapEntry]:
    """AI đề xuất tên mới cho các thuật ngữ đã duyệt. Dòng `locked` không bao
    giờ đổi; không `overwrite` thì chỉ điền dòng còn thiếu. Lỗi model/JSON →
    raise (tầng gọi quyết định bỏ qua hay báo lỗi). Commit khi xong."""
    repo = SkinMapRepository(db)
    params = variant.mode_params or {}
    keep = {str(n).strip().casefold() for n in (params.get("keep_names") or []) if str(n).strip()}
    terms = [
        t
        for t in GlossaryRepository(db).list_by_work(variant.work_id)
        if t.status == "approved" and t.target_term.strip()
    ]
    lines = [f"- {t.target_term} ({t.kind or 'other'})" for t in terms]
    excerpt = _full_excerpt(db, variant)
    if not lines and not excerpt.strip():
        return repo.list_by_variant(variant.id)  # type: ignore[arg-type]
    user = "NAMES AND TERMS:\n" + ("\n".join(lines) or "(none)")
    if excerpt.strip():
        user += f"\n\nEXCERPT OF THE CURRENT TRANSLATION:\n{excerpt}"
    raw = chat(build_skin_map_generate_prompt(params, variant.lang_tgt), user)
    items = parse_json_array(raw)

    kind_by_target = {t.target_term: t.kind for t in terms}
    existing = {e.original: e for e in repo.list_by_variant(variant.id)}  # type: ignore[arg-type]
    proposals: dict[str, tuple[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        orig = str(item.get("original") or "").strip()
        repl = str(item.get("replacement") or "").strip()
        if not orig or not repl or orig in proposals:
            continue
        kind = str(item.get("kind") or kind_by_target.get(orig) or "").strip().lower()
        if kind not in GLOSSARY_KINDS:
            kind = "other"
        proposals[orig] = (repl, kind)
    # Tên user dặn giữ nguyên: luôn có dòng replacement = original.
    for t in terms:
        if t.target_term.casefold() in keep and t.target_term not in proposals:
            proposals[t.target_term] = (t.target_term, t.kind or "character")

    total = len(existing)
    for orig, (repl, kind) in proposals.items():
        if orig.casefold() in keep:
            repl = orig
        cur = existing.get(orig)
        if cur is not None:
            if cur.locked or not overwrite:
                continue
            cur.replacement = repl[:255]
            cur.kind = kind
            repo.update(cur)
            continue
        if total >= _MAX_ROWS:
            continue
        repo.add(
            SkinMapEntry(
                id=None,
                variant_id=variant.id,  # type: ignore[arg-type]
                original=orig[:255],
                replacement=repl[:255],
                kind=kind,
            )
        )
        total += 1
    db.commit()
    return repo.list_by_variant(variant.id)  # type: ignore[arg-type]
