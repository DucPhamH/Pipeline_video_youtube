"""Parser EPUB: <div>/<li> là ngắt đoạn, encoding khai báo (GBK), tiêu đề
fallback h2 → mục lục → <title>."""
import io
import zipfile

from ebooklib import epub

from translate.infrastructure.parsers.epub import (
    _decode_html,
    _html_to_title_and_text,
    parse_epub,
)


def test_div_and_li_are_paragraph_breaks():
    title, text = _html_to_title_and_text(
        "<html><body><h2>Chương 2</h2><div>Đoạn một.</div><div>Đoạn hai.</div>"
        "<ul><li>Ý a</li><li>Ý b</li></ul></body></html>"
    )
    assert title == "Chương 2"
    assert text == "Đoạn một.\n\nĐoạn hai.\n\nÝ a\n\nÝ b"


def test_title_falls_back_to_toc_then_head_title_but_not_book_title():
    raw = "<html><head><title>Book</title></head><body><p>Body text only.</p></body></html>"
    assert _html_to_title_and_text(raw, toc_title="From TOC")[0] == "From TOC"
    assert _html_to_title_and_text(raw)[0] == "Book"
    assert _html_to_title_and_text(raw, book_title="Book")[0] == ""
    assert "Book" not in _html_to_title_and_text(raw)[1]  # <head> không lọt vào thân bài


def test_decode_honours_declared_encoding():
    xml = '<?xml version="1.0" encoding="gbk"?><html><body><p>你好世界</p></body></html>'
    assert "你好世界" in _decode_html(xml.encode("gbk"))
    meta = '<html><head><meta charset="big5"></head><body><p>繁體中文</p></body></html>'
    assert "繁體中文" in _decode_html(meta.encode("big5"))
    assert "Việt" in _decode_html("<p>Việt</p>".encode("utf-8"))


def _gbk_epub() -> bytes:
    book = epub.EpubBook()
    book.set_identifier("gbk")
    book.set_title("GBK Book")
    book.set_language("zh")
    ch = epub.EpubHtml(title="第一章 开始", file_name="c1.xhtml", lang="zh")
    ch.content = "<html><body><p>placeholder</p></body></html>"
    book.add_item(ch)
    book.toc = (epub.Link("c1.xhtml", "第一章 开始", "c1"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [ch]
    buf = io.BytesIO()
    epub.write_epub(buf, book)

    # Ghi đè chương bằng bytes GBK gốc (ebooklib luôn ghi UTF-8).
    raw = (
        '<?xml version="1.0" encoding="gbk"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>GBK Book</title></head>'
        "<body><div>这是第一段，内容足够长可以被解析器保留下来，不会被当成空白页丢掉。</div><div>这是第二段。</div></body></html>"
    ).encode("gbk")
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("c1.xhtml"):
                data = raw
            dst.writestr(info, data)
    return out.getvalue()


def test_parse_epub_gbk_chapter_with_toc_title():
    _, _, chapters = parse_epub(_gbk_epub())
    assert len(chapters) == 1
    assert chapters[0].title == "第一章 开始"
    assert chapters[0].text == "这是第一段，内容足够长可以被解析器保留下来，不会被当成空白页丢掉。\n\n这是第二段。"
