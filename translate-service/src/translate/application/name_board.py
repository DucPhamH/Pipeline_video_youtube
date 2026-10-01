"""Bảng duyệt tên — liệt kê tên + độ phủ, AI đề xuất tên (candidate), duyệt."""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from translate.application.llm_json import parse_json_array
from translate.application.modes import build_names_extract_prompt
from translate.application.name_apply import build_pattern, count_hits
from translate.domain.entities import GLOSSARY_KINDS, GlossaryTerm, SegmentStatus
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    GlossaryRepository,
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)

ChatFn = Callable[[str, str], str]

SAMPLE_DEFAULT = 12
SAMPLE_MAX = 40
_CHAPTER_CHARS = 1500
_BATCH_CHARS = 9000
_MAX_ADDED = 200


def list_names(db: Session, *, work_id: int) -> list[dict]:
    terms = GlossaryRepository(db).list_by_work(work_id)
    chapters = ChapterSourceRepository(db).list_by_work(work_id)
    targets = [t.target_term for t in terms if t.target_term.strip()]
    pattern = build_pattern(targets)

    # Mỗi variant: số segment có output chứa từng target (1 lượt regex/segment).
    hits_by_variant: list[tuple[int, str, dict[str, int]]] = []
    job_repo = JobRepository(db)
    seg_repo = SegmentRepository(db)
    for v in sorted(VariantRepository(db).list_by_work(work_id), key=lambda x: x.id or 0):
        counts: dict[str, int] = {}
        job = job_repo.latest_output_job_for_variant(v.id)  # type: ignore[arg-type]
        if job is not None and pattern is not None:
            for seg in seg_repo.list_by_job(job.id):  # type: ignore[arg-type]
                if seg.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
                    continue
                for name in count_hits(seg.output_text or "", pattern):
                    counts[name] = counts.get(name, 0) + 1
        hits_by_variant.append((v.id, v.mode, counts))  # type: ignore[arg-type]

    out = []
    for t in terms:
        src = t.source_term
        out.append(
            {
                "id": t.id,
                "source_term": src,
                "target_term": t.target_term,
                "kind": t.kind,
                "status": t.status,
                "notes": t.notes,
                "protected": t.protected,
                "source_chapter_count": sum(1 for ch in chapters if src and src in (ch.text or "")),
                "output_hits": (
                    [
                        {"variant_id": vid, "mode": mode, "segments": counts.get(t.target_term, 0)}
                        for vid, mode, counts in hits_by_variant
                    ]
                    if t.target_term.strip()
                    else []
                ),
            }
        )
    return out


def _even_sample(items: list, n: int) -> list:
    if n >= len(items):
        return list(items)
    if n <= 1:
        return [items[0]]
    picks = sorted({round(i * (len(items) - 1) / (n - 1)) for i in range(n)})
    return [items[i] for i in picks]


def _batches(blocks: list[str]) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    size = 0
    for b in blocks:
        if cur and size + len(b) > _BATCH_CHARS:
            out.append("\n\n---\n\n".join(cur))
            cur, size = [], 0
        cur.append(b)
        size += len(b)
    if cur:
        out.append("\n\n---\n\n".join(cur))
    return out


def extract_names(db: Session, *, work_id: int, chat: ChatFn, sample_chapters: int = SAMPLE_DEFAULT) -> dict:
    """AI trích tên từ chương nguồn rải đều CẢ sách (vài lệnh gọi gộp). Chỉ
    thêm source_term mới (status=candidate). Mọi lệnh gọi đều lỗi → raise."""
    work = WorkRepository(db).get(work_id)
    if work is None:
        raise LookupError(f"Work {work_id} không tồn tại")
    n = max(1, min(int(sample_chapters or SAMPLE_DEFAULT), SAMPLE_MAX))
    chapters = [c for c in ChapterSourceRepository(db).list_by_work(work_id) if (c.text or "").strip()]
    if not chapters:
        raise ValueError("Work không có chương nguồn")
    blocks = [f"CHAPTER {c.index}:\n{c.text[:_CHAPTER_CHARS]}" for c in _even_sample(chapters, n)]

    system = build_names_extract_prompt(work.lang_src, work.lang_tgt)
    proposals: dict[str, tuple[str, str, str]] = {}  # casefold -> (src, tgt, kind)
    errors: list[Exception] = []
    calls = 0
    for user in _batches(blocks):
        calls += 1
        try:
            items = parse_json_array(chat(system, user))
        except ValueError as exc:
            errors.append(exc)
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            src = str(item.get("source_term") or "").strip()[:255]
            tgt = str(item.get("target_term") or "").strip()[:255]
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in GLOSSARY_KINDS:
                kind = "other"
            if src and src.casefold() not in proposals:
                proposals[src.casefold()] = (src, tgt, kind)
    if calls and len(errors) == calls:
        raise errors[0]

    repo = GlossaryRepository(db)
    existing = {t.source_term.strip().casefold() for t in repo.list_by_work(work_id)}
    added = 0
    for key, (src, tgt, kind) in proposals.items():
        if key in existing or added >= _MAX_ADDED:
            continue
        repo.add(
            GlossaryTerm(
                id=None,
                work_id=work_id,
                source_term=src,
                target_term=tgt,
                kind=kind,
                status="candidate",
                notes="AI đề xuất (bảng duyệt tên)",
            )
        )
        existing.add(key)
        added += 1
    db.commit()
    return {"added": added, "terms": list_names(db, work_id=work_id)}


def approve_names(db: Session, *, work_id: int, term_ids: list[int]) -> list[dict]:
    repo = GlossaryRepository(db)
    for tid in dict.fromkeys(term_ids):
        term = repo.get(tid)
        if term is None or term.work_id != work_id:
            raise LookupError(f"Glossary term {tid} không tồn tại")
        if term.status != "approved":
            term.status = "approved"
            repo.update(term)
    db.commit()
    return list_names(db, work_id=work_id)
