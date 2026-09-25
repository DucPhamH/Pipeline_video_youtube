"""Import TXT → Work + ChapterSource + Variant(mode=full)."""
from __future__ import annotations

from dataclasses import dataclass

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
from translate.infrastructure.parsers.txt import split_txt_chapters
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    VariantRepository,
    WorkRepository,
)


@dataclass
class ImportTxtResult:
    work: Work
    chapters: list[ChapterSource]
    variant: Variant


def import_txt(
    db: Session,
    *,
    title: str,
    text: str,
    lang_src: str,
    author: str = "",
    lang_tgt: str = "vi",
) -> ImportTxtResult:
    parsed = split_txt_chapters(text)
    if not parsed:
        raise ValueError("Không có nội dung để import")

    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    variant_repo = VariantRepository(db)

    work = work_repo.add(
        Work(
            id=None,
            title=(title or "").strip() or "Untitled",
            author=(author or "").strip(),
            lang_src=lang_src or "zh",
            lang_tgt=lang_tgt or "vi",
            source_type=SourceType.UPLOAD,
            status=WorkStatus.READY,
        )
    )

    chapters = chapter_repo.add_many(
        [
            ChapterSource(
                id=None,
                work_id=work.id,  # type: ignore[arg-type]
                index=p.index,
                title=p.title,
                text=p.text,
                fingerprint=content_fingerprint(p.text),
            )
            for p in parsed
        ]
    )

    variant = variant_repo.add(
        Variant(
            id=None,
            work_id=work.id,  # type: ignore[arg-type]
            mode="full",
            status=VariantStatus.PENDING,
            lang_tgt=work.lang_tgt,
        )
    )
    db.commit()
    return ImportTxtResult(work=work, chapters=chapters, variant=variant)
