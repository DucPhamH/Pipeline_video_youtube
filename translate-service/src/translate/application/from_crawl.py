"""Handoff từ crawl — idempotent theo external_id + fingerprint sync."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from translate.application.fingerprint import content_fingerprint
from translate.domain.entities import (
    ChapterSource,
    SourceType,
    Variant,
    VariantStatus,
    Work,
    WorkStatus,
)
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    VariantRepository,
    WorkRepository,
)


@dataclass
class HandoffChapterIn:
    index: int
    title: str
    text: str
    fingerprint: str = ""


@dataclass
class FromCrawlResult:
    work: Work
    chapters: list[ChapterSource]
    variant: Variant
    created: bool
    changed_chapter_indices: list[int] = field(default_factory=list)


def from_crawl(
    db: Session,
    *,
    external_id: str,
    title: str,
    author: str,
    lang_src: str,
    lang_tgt_hint: str,
    chapters: list[HandoffChapterIn],
    callback_url: str | None = None,
    missing_cleaned: int = 0,
    unreviewed: int = 0,
) -> FromCrawlResult:
    if not external_id:
        raise ValueError("external_id bắt buộc")
    if not chapters:
        raise ValueError("chapters trống")

    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    variant_repo = VariantRepository(db)

    existing = work_repo.get_by_external_id(external_id)
    lang_tgt = lang_tgt_hint or "vi"
    cb = (callback_url or "").strip() or None

    built = [
        ChapterSource(
            id=None,
            work_id=0,
            index=c.index,
            title=c.title or f"Chapter {c.index}",
            text=c.text or "",
            fingerprint=c.fingerprint or content_fingerprint(c.text or ""),
        )
        for c in chapters
    ]

    if existing is not None:
        old_chapters = chapter_repo.list_by_work(existing.id)  # type: ignore[arg-type]
        old_fps = {c.index: c.fingerprint for c in old_chapters}
        new_indices = {c.index for c in built}
        changed = [
            c.index
            for c in built
            if old_fps.get(c.index) != c.fingerprint
        ]
        changed.extend(sorted(i for i in old_fps if i not in new_indices))
        changed = sorted(set(changed))

        existing.title = title or existing.title
        existing.author = author or existing.author
        existing.lang_src = lang_src or existing.lang_src
        existing.lang_tgt = lang_tgt
        existing.status = WorkStatus.READY
        if cb:
            existing.callback_url = cb
        existing.missing_cleaned = max(0, missing_cleaned)
        existing.unreviewed_chapters = max(0, unreviewed)
        work_repo.update(existing)
        saved = chapter_repo.replace_for_work(existing.id, built)  # type: ignore[arg-type]
        variants = variant_repo.list_by_work(existing.id)  # type: ignore[arg-type]
        full = next((v for v in variants if v.mode == "full"), None)
        if full is None:
            full = variant_repo.add(
                Variant(
                    id=None,
                    work_id=existing.id,  # type: ignore[arg-type]
                    mode="full",
                    status=VariantStatus.PENDING,
                    lang_tgt=lang_tgt,
                )
            )
        else:
            full.lang_tgt = lang_tgt
            if changed:
                full.status = VariantStatus.PENDING
            variant_repo.update(full)
        if changed:
            for v in variant_repo.list_by_work(existing.id):  # type: ignore[arg-type]
                if v.status == VariantStatus.READY and v.id is not None:
                    variant_repo.update_status(v.id, VariantStatus.PENDING)
        db.commit()
        return FromCrawlResult(
            work=existing,
            chapters=saved,
            variant=full,
            created=False,
            changed_chapter_indices=changed,
        )

    work = work_repo.add(
        Work(
            id=None,
            external_id=external_id,
            title=title or "Untitled",
            author=author or "",
            lang_src=lang_src or "zh",
            lang_tgt=lang_tgt,
            source_type=SourceType.CRAWL_HANDOFF,
            status=WorkStatus.READY,
            callback_url=cb,
            missing_cleaned=max(0, missing_cleaned),
            unreviewed_chapters=max(0, unreviewed),
        )
    )
    for ch in built:
        ch.work_id = work.id  # type: ignore[assignment]
    saved = chapter_repo.add_many(built)
    variant = variant_repo.add(
        Variant(
            id=None,
            work_id=work.id,  # type: ignore[arg-type]
            mode="full",
            status=VariantStatus.PENDING,
            lang_tgt=lang_tgt,
        )
    )
    db.commit()
    return FromCrawlResult(
        work=work,
        chapters=saved,
        variant=variant,
        created=True,
        changed_chapter_indices=[c.index for c in saved],
    )
