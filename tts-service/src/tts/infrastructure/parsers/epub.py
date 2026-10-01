"""Đọc EPUB thành chương văn bản. Bỏ mục lục và trang gần như rỗng."""
from __future__ import annotations

import io
import re
from html import unescape

from ebooklib import ITEM_COVER, ITEM_DOCUMENT, ITEM_IMAGE, epub

from tts.infrastructure.parsers.txt import ParsedChapter

_SKIP_NAMES = {"nav.xhtml", "toc.xhtml", "nav.html", "toc.html"}
_TAG_RE = re.compile(r"<[^>]+>")
_H1_RE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")


def _html_to_title_and_text(raw: str) -> tuple[str, str]:
    title = ""
    match = _H1_RE.search(raw)
    if match:
        title = unescape(_TAG_RE.sub("", match.group(1))).strip()
    body = _H1_RE.sub(" ", raw)
    body = re.sub(r"(?is)<script.*?>.*?</script>", " ", body)
    body = re.sub(r"(?is)<style.*?>.*?</style>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</p>", "\n\n", body)
    body = re.sub(r"(?i)</h[1-6]>", "\n\n", body)
    body = unescape(_TAG_RE.sub(" ", body))
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]{2,}", " ", body).strip()
    return title, body


def _meta(book: epub.EpubBook, name: str) -> str:
    values = book.get_metadata("DC", name) or []
    if not values:
        return ""
    first = values[0]
    text = first[0] if isinstance(first, tuple) else first
    return str(text or "").strip()


def _spine_documents(book: epub.EpubBook) -> list:
    docs = []
    for entry in book.spine:
        idref = entry[0] if isinstance(entry, tuple) else entry
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        name = (item.get_name() or "").rsplit("/", 1)[-1].lower()
        if name in _SKIP_NAMES:
            continue
        docs.append(item)
    if docs:
        return docs
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        name = (item.get_name() or "").rsplit("/", 1)[-1].lower()
        if name not in _SKIP_NAMES:
            docs.append(item)
    return docs


def _cover(book: epub.EpubBook) -> bytes:
    for item in book.get_items_of_type(ITEM_COVER):
        data = item.get_content()
        if data:
            return data
    for item in book.get_items_of_type(ITEM_IMAGE):
        name = (item.get_name() or "").lower()
        if "cover" in name:
            data = item.get_content()
            if data:
                return data
    return b""


def parse_epub(data: bytes) -> tuple[str, str, list[ParsedChapter], bytes]:
    book = epub.read_epub(io.BytesIO(data))
    title = _meta(book, "title")
    author = _meta(book, "creator")
    chapters: list[ParsedChapter] = []
    for item in _spine_documents(book):
        raw = item.get_content().decode("utf-8", errors="replace")
        chapter_title, text = _html_to_title_and_text(raw)
        if len(text) < 30:
            continue
        chapters.append(
            ParsedChapter(
                index=len(chapters) + 1,
                title=chapter_title or f"Chapter {len(chapters) + 1}",
                text=text,
            )
        )
    return title, author, chapters, _cover(book)
