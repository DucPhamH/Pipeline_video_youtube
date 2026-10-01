"""Export bản dịch EPUB từ Variant (segment mới nhất completed)."""
from __future__ import annotations

import html
import io

from ebooklib import epub
from sqlalchemy.orm import Session

from translate.domain.entities import JobStatus, SegmentStatus
from translate.infrastructure.persistence.models import JobModel
from translate.infrastructure.persistence.repositories import (
    ChapterSourceRepository,
    JobRepository,
    SegmentRepository,
    VariantRepository,
    WorkRepository,
)


def export_variant_epub(db: Session, *, variant_id: int, bilingual: bool = False) -> bytes:
    variant = VariantRepository(db).get(variant_id)
    if variant is None:
        raise LookupError(f"Variant {variant_id} không tồn tại")
    work = WorkRepository(db).get(variant.work_id)
    if work is None:
        raise LookupError("Work missing")

    row = (
        db.query(JobModel)
        .filter(JobModel.variant_id == variant_id, JobModel.status == JobStatus.COMPLETED.value)
        .order_by(JobModel.id.desc())
        .first()
    )
    if row is None:
        raise LookupError("Chưa có job completed để export")

    job = JobRepository(db).get(row.id)
    assert job is not None
    chapters = {c.index: c for c in ChapterSourceRepository(db).list_by_work(work.id)}  # type: ignore[arg-type]

    book = epub.EpubBook()
    book.set_identifier(f"variant-{variant_id}")
    book.set_title(work.title or "untitled")
    book.set_language(variant.lang_tgt or "vi")
    book.add_author(work.author or "Unknown")

    spine: list = ["nav"]
    toc = []
    n = 0
    for seg in SegmentRepository(db).list_by_job(job.id):  # type: ignore[arg-type]
        if seg.status not in (SegmentStatus.DONE, SegmentStatus.SKIPPED_CACHE):
            continue
        n += 1
        ch = chapters.get(seg.chapter_index)
        title = (ch.title if ch else "") or f"Chapter {seg.chapter_index}"
        translated = html.escape(seg.output_text or "").replace("\n", "<br/>\n")
        if bilingual:
            source = html.escape(seg.source_text or "").replace("\n", "<br/>\n")
            body = (
                "<table><tr>"
                f'<td class="src"><p>{source}</p></td>'
                f'<td class="tgt"><p>{translated}</p></td>'
                "</tr></table>"
            )
        else:
            body = f"<p>{translated}</p>"
        chapter = epub.EpubHtml(
            title=title,
            file_name=f"chap_{n:04d}.xhtml",
            lang=variant.lang_tgt or "vi",
        )
        chapter.content = (
            "<html><head><title>"
            f"{html.escape(title)}</title>"
            "<style>table{width:100%;border-collapse:collapse}"
            "td{width:50%;vertical-align:top;padding:8px}"
            "td.src{border-right:1px solid #ccc}</style></head>"
            f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
        )
        book.add_item(chapter)
        spine.append(chapter)
        toc.append(chapter)

    if not toc:
        raise LookupError("Không có chương đã dịch để xuất EPUB")

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()
