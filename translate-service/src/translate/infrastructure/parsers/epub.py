"""Đọc EPUB thành chương văn bản. Bỏ mục lục và trang gần như rỗng."""
from __future__ import annotations

import codecs
import io
import posixpath
import re
from html import unescape
from urllib.parse import unquote

from ebooklib import ITEM_DOCUMENT, ITEM_NAVIGATION, epub

from translate.infrastructure.parsers.txt import ParsedChapter

_SKIP_NAMES = {"nav.xhtml", "toc.xhtml", "nav.html", "toc.html"}
_TAG_RE = re.compile(r"<[^>]+>")
_H1_RE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
_H2_RE = re.compile(r"(?is)<h2[^>]*>(.*?)</h2>")
_H3_RE = re.compile(r"(?is)<h3[^>]*>(.*?)</h3>")
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_HEAD_RE = re.compile(r"(?is)<head[^>]*>.*?</head>")
# Thẻ khối — nhiều EPUB (nhất là convert từ web novel) chia đoạn bằng <div>
# hoặc <li> thay vì <p>; không coi là ngắt đoạn thì cả chương dính 1 khối.
_BLOCK_END_RE = re.compile(r"(?i)</(?:p|div|li|blockquote|section|article|tr|dd|dt|pre|h[1-6])\s*>|<hr\b[^>]*>")
_XML_ENCODING_RE = re.compile(rb"""^\s*<\?xml[^>]*\bencoding\s*=\s*["']([A-Za-z0-9._:-]+)["']""")
_META_CHARSET_RE = re.compile(rb"""(?i)<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9._:-]+)""")


def _decode_html(data: bytes) -> str:
    """Giải mã theo encoding khai báo (BOM → <?xml encoding> → <meta charset>),
    mặc định UTF-8 — EPUB cũ (nhất là tiếng Trung) hay dùng GBK/Big5."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    head = data[:2048]
    match = _XML_ENCODING_RE.search(head) or _META_CHARSET_RE.search(head)
    if match:
        name = match.group(1).decode("ascii", errors="ignore")
        try:
            codec = codecs.lookup(name).name
        except LookupError:
            codec = ""
        # UTF-16 khai báo nhưng không BOM thường là khai báo sai — giữ UTF-8.
        if codec and not codec.startswith("utf-16"):
            if codec in ("gb2312", "gbk"):
                codec = "gb18030"  # superset — tránh lỗi ký tự ngoài GB2312
            return data.decode(codec, errors="replace")
    return data.decode("utf-8", errors="replace")


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub("", fragment))).strip()


def _html_to_title_and_text(
    raw: str, *, toc_title: str = "", book_title: str = ""
) -> tuple[str, str]:
    title = ""
    match = _H1_RE.search(raw)
    body = _HEAD_RE.sub(" ", raw)
    if match:
        title = _strip_tags(match.group(1))
        # Chỉ bỏ đúng <h1> dùng làm tiêu đề — các <h1> khác là nội dung.
        first = _H1_RE.search(body)
        if first:
            body = body[: first.start()] + " " + body[first.end():]
    if not title:
        # Không có <h1>: thử h2/h3 (chỉ bỏ đúng heading dùng làm tiêu đề khỏi
        # thân bài), rồi tiêu đề trong mục lục, rồi <title> trong <head> (bỏ
        # qua nếu chỉ là tên sách — nhiều EPUB đặt <title> giống nhau mọi chương).
        for heading_re in (_H2_RE, _H3_RE):
            match = heading_re.search(body)
            if match and _strip_tags(match.group(1)):
                title = _strip_tags(match.group(1))
                body = body[: match.start()] + " " + body[match.end():]
                break
    if not title:
        title = (toc_title or "").strip()
    if not title:
        match = _TITLE_RE.search(raw)
        if match and _strip_tags(match.group(1)) != (book_title or "").strip():
            title = _strip_tags(match.group(1))
    body = re.sub(r"(?is)<script.*?>.*?</script>", " ", body)
    body = re.sub(r"(?is)<style.*?>.*?</style>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = _BLOCK_END_RE.sub("\n\n", body)
    body = _TAG_RE.sub(" ", body)
    body = unescape(body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n[ \t]+", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]{2,}", " ", body).strip()
    return title, body


def _toc_base_dirs(book: epub.EpubBook) -> list[str]:
    """Thư mục chứa file NCX/nav (tương đối OPF, như item.get_name()) — href
    trong mục lục tương đối với file mục lục, không phải với OPF."""
    dirs: list[str] = []
    for item in book.get_items():
        try:
            is_toc = item.get_type() == ITEM_NAVIGATION or isinstance(item, epub.EpubNav)
        except Exception:  # noqa: BLE001
            is_toc = False
        if is_toc:
            d = posixpath.dirname(item.get_name() or "")
            if d not in dirs:
                dirs.append(d)
    return dirs


def _resolve_toc_href(href: str, *, names: set[str], base_dirs: list[str]) -> str:
    """href mục lục → tên item trong sách. ebooklib đã ghép thư mục nav cho
    EPUB3 nhưng không ghép cho NCX, và không url-decode (`%20`…)."""
    path = unquote(str(href).split("#", 1)[0])
    candidates = [posixpath.normpath(path)] if path else []
    for d in base_dirs:
        if path:
            candidates.append(posixpath.normpath(posixpath.join(d, path)))
    for cand in candidates:
        if cand in names:
            return cand
    return candidates[0] if candidates else ""


def _toc_titles(book: epub.EpubBook) -> dict[str, str]:
    """file_name → tiêu đề trong mục lục (NCX/nav) — fallback cuối cho chương
    không có heading nào."""
    out: dict[str, str] = {}
    names = {item.get_name() for item in book.get_items() if item.get_name()}
    base_dirs = _toc_base_dirs(book)

    def walk(entries) -> None:
        for entry in entries or []:
            if isinstance(entry, (tuple, list)):
                if entry:
                    walk([entry[0]])
                if len(entry) > 1:
                    walk(entry[1])
                continue
            href = getattr(entry, "href", None) or getattr(entry, "file_name", None)
            title = getattr(entry, "title", None)
            if href and title:
                key = _resolve_toc_href(str(href), names=names, base_dirs=base_dirs)
                if key:
                    out.setdefault(key, str(title).strip())

    try:
        walk(book.toc)
    except Exception:  # noqa: BLE001 — mục lục hỏng thì bỏ qua
        return {}
    return out


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


def parse_epub(data: bytes) -> tuple[str, str, list[ParsedChapter]]:
    book = epub.read_epub(io.BytesIO(data))
    title = _meta(book, "title")
    author = _meta(book, "creator")
    chapters: list[ParsedChapter] = []
    toc = _toc_titles(book)
    for item in _spine_documents(book):
        # `item.content` = bytes gốc trong file. `get_content()` của EpubHtml
        # dựng lại qua lxml, làm hỏng file không phải UTF-8 và bỏ mất <title>.
        data = item.content if isinstance(item.content, bytes) and item.content else item.get_content()
        raw = _decode_html(data) if isinstance(data, bytes) else str(data or "")
        chapter_title, text = _html_to_title_and_text(
            raw, toc_title=toc.get(item.get_name() or "", ""), book_title=title
        )
        if len(text) < 30:
            continue
        chapters.append(
            ParsedChapter(
                index=len(chapters) + 1,
                title=chapter_title or f"Chapter {len(chapters) + 1}",
                text=text,
            )
        )
    return title, author, chapters
