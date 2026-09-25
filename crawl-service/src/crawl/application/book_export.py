"""Xuất sách TXT / EPUB — ebooklib (EPUB chuẩn, dùng rộng trong lncrawl-class tools)."""
from __future__ import annotations

import html
import io
import zipfile
from dataclasses import dataclass

from crawl.application.excel_export import ChapterExportRow, sanitize_filename


@dataclass
class NovelExportMeta:
    title: str
    author: str = ""
    source_key: str = ""
    source_url: str = ""


def build_novel_txt(meta: NovelExportMeta, rows: list[ChapterExportRow]) -> bytes:
    parts: list[str] = [meta.title.strip() or "untitled"]
    if meta.author:
        parts.append(f"作者 / Author: {meta.author}")
    if meta.source_url:
        parts.append(meta.source_url)
    parts.append("")
    parts.append("=" * 40)
    parts.append("")
    for row in rows:
        title = (row.title or "").strip() or "(không tiêu đề)"
        body = (row.content or "").strip()
        parts.append(title)
        parts.append("-" * min(40, max(8, len(title))))
        parts.append(body)
        parts.append("")
        parts.append("")
    text = "\n".join(parts).rstrip() + "\n"
    return text.encode("utf-8")


def build_novel_epub(meta: NovelExportMeta, rows: list[ChapterExportRow]) -> bytes:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(meta.source_url or sanitize_filename(meta.title) or "novel")
    book.set_title(meta.title or "untitled")
    book.set_language("zh")
    book.add_author(meta.author or "Unknown")
    if meta.source_url:
        book.add_metadata("DC", "source", meta.source_url)

    spine: list = ["nav"]
    toc = []
    for i, row in enumerate(rows, start=1):
        title = (row.title or "").strip() or f"Chapter {i}"
        body = html.escape(row.content or "").replace("\n", "<br/>\n")
        chapter = epub.EpubHtml(
            title=title,
            file_name=f"chap_{i:04d}.xhtml",
            lang="zh",
        )
        chapter.content = (
            f"<html><head><title>{html.escape(title)}</title></head>"
            f"<body><h1>{html.escape(title)}</h1><p>{body}</p></body></html>"
        )
        book.add_item(chapter)
        spine.append(chapter)
        toc.append(chapter)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def build_novel_bundle_zip(
    meta: NovelExportMeta,
    rows: list[ChapterExportRow],
    *,
    include_xlsx: bool = True,
) -> bytes:
    """Zip: .txt + .epub (+ .xlsx nếu có openpyxl path)."""
    from crawl.application.excel_export import build_novel_workbook

    base = sanitize_filename(meta.title)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}.txt", build_novel_txt(meta, rows))
        zf.writestr(f"{base}.epub", build_novel_epub(meta, rows))
        if include_xlsx:
            zf.writestr(f"{base}.xlsx", build_novel_workbook(rows))
    return buf.getvalue()
