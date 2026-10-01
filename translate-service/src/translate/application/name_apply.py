"""Áp tên mới lên chương ĐÃ dịch mà không dịch lại (bảng duyệt tên + bảng đổi vỏ).

Engine thay thế 1 lượt duy nhất: regex alternation mọi tên cũ (dài trước), nên
A→B và B→C trong cùng 1 lô không bị nối chuỗi (A không thành C). Ranh giới từ
Unicode `(?<![\\w])…(?![\\w])` — `\\w` của Python khớp cả chữ tiếng Việt có dấu,
nên "Lan" không khớp trong "Lành". Phân biệt hoa/thường.

Mỗi lô (không dry-run) lưu snapshot output cũ/mới từng segment để Undo; Undo chỉ
khôi phục segment mà output hiện tại vẫn đúng bằng bản lô đã ghi (user sửa tay
sau đó thì bỏ qua, không đè).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from translate.domain.entities import SegmentStatus, Variant
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    GlossaryRepository,
    JobRepository,
    NameApplyBatchRepository,
    SegmentRepository,
    SkinMapRepository,
    TranslationCacheRepository,
    VariantRepository,
)

_OUTPUT_STATUSES = (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE)
_MAX_SAMPLES = 20
_SNIPPET_CHARS = 140
_SNIPPET_LEAD = 50


class ApplyConflict(RuntimeError):
    """Variant đang có job chạy/xếp hàng — router trả 409."""


@dataclass
class NameChange:
    key_id: int  # term_id (glossary) hoặc row_id (skin_map)
    old: str
    new: str


# --- Engine thuần (không DB) ------------------------------------------------


def build_pattern(olds: list[str]) -> re.Pattern | None:
    terms = sorted({o for o in olds if o}, key=lambda x: (-len(x), x))
    if not terms:
        return None
    alt = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"(?<![\w])(?:{alt})(?![\w])")


def replace_names(text: str, mapping: dict[str, str], pattern: re.Pattern | None = None) -> tuple[str, dict[str, int]]:
    """Thay 1 lượt; trả (text mới, số lần thay theo tên cũ)."""
    pat = pattern or build_pattern(list(mapping))
    counts: dict[str, int] = {}
    if pat is None or not text:
        return text, counts

    def _sub(m: re.Match) -> str:
        old = m.group(0)
        counts[old] = counts.get(old, 0) + 1
        return mapping[old]

    return pat.sub(_sub, text), counts


def count_hits(text: str, pattern: re.Pattern | None) -> set[str]:
    """Tên nào (trong pattern) xuất hiện trong text — cùng ngữ nghĩa với replace."""
    if pattern is None or not text:
        return set()
    return {m.group(0) for m in pattern.finditer(text)}


def _snippets(before: str, after: str, pattern: re.Pattern) -> tuple[str, str]:
    m = pattern.search(before)
    start = max(0, (m.start() if m else 0) - _SNIPPET_LEAD)
    # Phần trước lần khớp đầu không đổi → cùng offset ở cả 2 bản.
    return before[start : start + _SNIPPET_CHARS], after[start : start + _SNIPPET_CHARS]


# --- Dịch vụ DB ---------------------------------------------------------------


def _ensure_idle(db: Session, variant_ids: list[int]) -> None:
    job_repo = JobRepository(db)
    busy = [vid for vid in variant_ids if job_repo.has_active_for_variant(vid)]
    if busy:
        raise ApplyConflict(
            f"Variant #{busy[0]} đang có job chạy/xếp hàng — dừng job trước khi áp tên"
        )


def _output_segments(db: Session, variant: Variant):
    job = JobRepository(db).latest_output_job_for_variant(variant.id)  # type: ignore[arg-type]
    if job is None:
        return []
    return [
        s
        for s in SegmentRepository(db).list_by_job(job.id)  # type: ignore[arg-type]
        if s.status in _OUTPUT_STATUSES and s.output_text
    ]


def _validate_changes(changes: list[NameChange]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for c in changes:
        if not (c.new or "").strip():
            raise ValueError("Tên mới không được để trống")
        c.new = c.new.strip()
        if not c.old or c.old == c.new:
            continue
        if c.old in mapping and mapping[c.old] != c.new:
            raise ValueError(f"'{c.old}' được đổi sang 2 tên khác nhau trong cùng 1 lô")
        mapping[c.old] = c.new
    return mapping


def _run(
    db: Session,
    *,
    work_id: int,
    variants: list[Variant],
    changes: list[NameChange],
    dry_run: bool,
    kind: str,
    batch_variant_id: int | None,
    commit_meta,
    extra_changes_meta=None,
) -> dict:
    mapping = _validate_changes(changes)
    pattern = build_pattern(list(mapping))
    chapters = {c.index: c for c in ChapterSourceRepository(db).list_by_work(work_id)}
    seg_repo = SegmentRepository(db)
    cache_repo = TranslationCacheRepository(db)

    seg_hits: dict[str, int] = {}
    rep_hits: dict[str, int] = {}
    samples: list[dict] = []
    rows: list[tuple[int, str, str]] = []
    if pattern is not None:
        for v in variants:
            for seg in _output_segments(db, v):
                before = seg.output_text or ""
                after, counts = replace_names(before, mapping, pattern)
                if not counts:
                    continue
                for old, n in counts.items():
                    seg_hits[old] = seg_hits.get(old, 0) + 1
                    rep_hits[old] = rep_hits.get(old, 0) + n
                if len(samples) < _MAX_SAMPLES:
                    b, a = _snippets(before, after, pattern)
                    ch = chapters.get(seg.chapter_index)
                    samples.append(
                        {
                            "segment_id": seg.id,
                            "variant_id": v.id,
                            "chapter_index": seg.chapter_index,
                            "title": (ch.title if ch else "") or "",
                            "before": b,
                            "after": a,
                        }
                    )
                rows.append((seg.id, before, after))  # type: ignore[arg-type]
                if not dry_run:
                    seg.output_text = after
                    seg_repo.update(seg)
                    # Như PUT segment: thay luôn entry cache, không thì job sau
                    # hit cache và lấy lại tên cũ.
                    if seg.cache_key:
                        cache_repo.put(seg.cache_key, after)

    seen: set[str] = set()
    per_term = []
    for c in changes:
        counted = c.old in mapping and c.old not in seen
        if counted:
            seen.add(c.old)
        per_term.append(
            {
                "term_id": c.key_id,
                "old_target": c.old,
                "new_target": c.new,
                "segments": seg_hits.get(c.old, 0) if counted else 0,
                "replacements": rep_hits.get(c.old, 0) if counted else 0,
            }
        )

    batch_id = None
    if not dry_run:
        meta = extra_changes_meta() if extra_changes_meta else {}
        commit_meta()
        batch_id = NameApplyBatchRepository(db).add(
            work_id=work_id,
            variant_id=batch_variant_id,
            kind=kind,
            changes=[{"id": c.key_id, "old": c.old, "new": c.new, **meta.get(c.key_id, {})} for c in changes],
            rows=rows,
        )
        db.commit()
    return {
        "batch_id": batch_id,
        "total_replacements": sum(rep_hits.values()),
        "per_term": per_term,
        "samples": samples,
    }


def apply_glossary_changes(
    db: Session,
    *,
    work_id: int,
    changes: list[tuple[int, str]],
    variant_ids: list[int] | None,
    dry_run: bool,
) -> dict:
    gl_repo = GlossaryRepository(db)
    variant_repo = VariantRepository(db)
    all_variants = variant_repo.list_by_work(work_id)
    by_id = {v.id: v for v in all_variants}
    if variant_ids:
        missing = [vid for vid in variant_ids if vid not in by_id]
        if missing:
            raise LookupError(f"Variant {missing[0]} không thuộc Work {work_id}")
        targets = [by_id[vid] for vid in dict.fromkeys(variant_ids)]
    else:
        targets = all_variants

    terms = {}
    items: list[NameChange] = []
    for term_id, new in changes:
        term = gl_repo.get(term_id)
        if term is None or term.work_id != work_id:
            raise LookupError(f"Glossary term {term_id} không tồn tại")
        terms[term_id] = term
        items.append(NameChange(key_id=term_id, old=term.target_term, new=new))
    if not dry_run:
        _ensure_idle(db, [v.id for v in targets])  # type: ignore[misc]

    # Bảng đổi vỏ của variant reskin fork từ variant được áp: `original` là tên
    # trong bản full — đổi theo để map vẫn khớp bản full mới.
    target_ids = {v.id for v in targets}
    skin_repo = SkinMapRepository(db)
    skin_variants = [v for v in all_variants if v.mode == "reskin" and v.source_variant_id in target_ids]

    def _skin_meta() -> dict:
        meta: dict[int, dict] = {}
        for c in items:
            if not c.old or c.old == c.new:
                continue
            row_ids = []
            for v in skin_variants:
                vrows = skin_repo.list_by_variant(v.id)  # type: ignore[arg-type]
                if any(r.original == c.new for r in vrows):
                    continue  # đã có dòng cho tên mới — giữ nguyên, tránh trùng original
                for row in vrows:
                    if row.original == c.old:
                        row.original = c.new
                        skin_repo.update(row)
                        row_ids.append(row.id)
            if row_ids:
                meta[c.key_id] = {"skin_rows": row_ids}
        return meta

    def _commit_meta() -> None:
        for c in items:
            term = terms[c.key_id]
            term.target_term = c.new
            term.status = "approved"
            gl_repo.update(term)

    return _run(
        db,
        work_id=work_id,
        variants=targets,
        changes=items,
        dry_run=dry_run,
        kind="glossary",
        batch_variant_id=targets[0].id if len(targets) == 1 else None,
        commit_meta=_commit_meta,
        extra_changes_meta=_skin_meta,
    )


def apply_skin_map_changes(
    db: Session, *, variant_id: int, changes: list[tuple[int, str]], dry_run: bool
) -> dict:
    variant = VariantRepository(db).get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")
    skin_repo = SkinMapRepository(db)
    rows = {}
    items: list[NameChange] = []
    for row_id, new in changes:
        row = skin_repo.get(row_id)
        if row is None or row.variant_id != variant_id:
            raise LookupError(f"Dòng bảng đổi vỏ {row_id} không tồn tại")
        rows[row_id] = row
        items.append(NameChange(key_id=row_id, old=row.replacement, new=new))
    if not dry_run:
        _ensure_idle(db, [variant_id])

    def _commit_meta() -> None:
        for c in items:
            row = rows[c.key_id]
            row.replacement = c.new
            skin_repo.update(row)

    return _run(
        db,
        work_id=variant.work_id,
        variants=[variant],
        changes=items,
        dry_run=dry_run,
        kind="skin_map",
        batch_variant_id=variant_id,
        commit_meta=_commit_meta,
    )


def list_batches(db: Session, *, work_id: int, limit: int = 20) -> list[dict]:
    out = []
    for b in NameApplyBatchRepository(db).list_by_work(work_id, limit=limit):
        out.append(
            {
                "id": b["id"],
                "created_at": b["created_at"],
                "kind": b["kind"],
                "variant_id": b["variant_id"],
                "changes": [
                    {"old": str(c.get("old") or ""), "new": str(c.get("new") or "")}
                    for c in b["changes"]
                    if isinstance(c, dict)
                ],
                "segments": b["segments"],
            }
        )
    return out


def undo_batch(db: Session, *, work_id: int, batch_id: int) -> dict:
    batch_repo = NameApplyBatchRepository(db)
    batch = batch_repo.get(batch_id)
    if batch is None or batch["work_id"] != work_id:
        raise LookupError(f"Lô áp tên {batch_id} không tồn tại")
    seg_repo = SegmentRepository(db)
    job_repo = JobRepository(db)
    cache_repo = TranslationCacheRepository(db)
    rows = batch_repo.rows(batch_id)

    segs = {}
    for segment_id, _old, _new in rows:
        seg = seg_repo.get(segment_id)
        if seg is not None:
            segs[segment_id] = seg
    variant_ids = set()
    for seg in segs.values():
        job = job_repo.get(seg.job_id)
        if job is not None:
            variant_ids.add(job.variant_id)
    if batch["variant_id"] is not None:
        variant_ids.add(batch["variant_id"])
    _ensure_idle(db, sorted(variant_ids))

    restored = skipped = 0
    for segment_id, old, new in rows:
        seg = segs.get(segment_id)
        if seg is None or (seg.output_text or "") != new:
            skipped += 1
            continue
        seg.output_text = old
        seg_repo.update(seg)
        if seg.cache_key and seg.status in _OUTPUT_STATUSES:
            cache_repo.put(seg.cache_key, old)
        restored += 1

    gl_repo = GlossaryRepository(db)
    skin_repo = SkinMapRepository(db)
    for c in batch["changes"]:
        if not isinstance(c, dict):
            continue
        key_id, old, new = c.get("id"), str(c.get("old") or ""), str(c.get("new") or "")
        if not isinstance(key_id, int):
            continue
        if batch["kind"] == "glossary":
            term = gl_repo.get(key_id)
            if term is not None and term.work_id == work_id and term.target_term == new:
                term.target_term = old
                gl_repo.update(term)
            for row_id in c.get("skin_rows") or []:
                row = skin_repo.get(int(row_id))
                if row is not None and row.original == new:
                    row.original = old
                    skin_repo.update(row)
        else:
            row = skin_repo.get(key_id)
            if row is not None and row.replacement == new:
                row.replacement = old
                skin_repo.update(row)
    batch_repo.delete(batch_id)
    db.commit()
    return {"restored": restored, "skipped": skipped}
