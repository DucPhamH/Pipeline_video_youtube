"""Import EPUB → Work + ChapterSource + Variant(mode=full)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from translate.application.fingerprint import content_fingerprint
from translate.application.import_txt import ImportTxtResult
from translate.domain.entities import (
    ChapterSource,
    SourceType,
    Variant,
    VariantStatus,
    Work,
    WorkStatus,
)
from translate.infrastructure.parsers.epub import parse_epub
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    VariantRepository,
    WorkRepository,
)


def import_epub(
    db: Session,
    *,
    data: bytes,
    title: str = "",
    author: str = "",
    lang_src: str = "zh",
    lang_tgt: str = "vi",
) -> ImportTxtResult:
    epub_title, epub_author, parsed = parse_epub(data)
    if not parsed:
        raise ValueError("EPUB không có chương văn bản")

    work_repo = WorkRepository(db)
    chapter_repo = ChapterSourceRepository(db)
    variant_repo = VariantRepository(db)

    work = work_repo.add(
        Work(
            id=None,
            title=(title or "").strip() or epub_title or "Untitled",
            author=(author or "").strip() or epub_author,
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
