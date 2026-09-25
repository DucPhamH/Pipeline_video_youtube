"""Wenku8 chương ảnh — OCR khi text HTML rỗng."""
from bs4 import BeautifulSoup

from crawl.infrastructure.sources.wenku8_net_source import Wenku8NetSource


def test_collect_chapter_image_urls():
    html = """
    <div id="content">
      <div class="divimage"><img class="imagecontent" src="https://pic.example/a.jpg"/></div>
      <div class="divimage"><img src="//pic.example/b.jpg"/></div>
    </div>
    """
    node = BeautifulSoup(html, "lxml").select_one("#content")
    urls = Wenku8NetSource._collect_chapter_image_urls(node)
    assert urls == ["https://pic.example/a.jpg", "https://pic.example/b.jpg"]


def test_fetch_chapter_content_uses_ocr_when_text_empty(monkeypatch):
    src = Wenku8NetSource()
    html = """
    <html><body><div id="content">
      <div class="divimage"><img src="https://pic.example/1.jpg"/></div>
      <a href="#">返回书页</a>
    </div></body></html>
    """

    monkeypatch.setattr(src, "_get_soup", lambda _url: BeautifulSoup(html, "lxml"))

    def fake_tls(url, **kwargs):
        assert url == "https://pic.example/1.jpg"
        return 200, b"\xff\xd8\xff" + b"x" * 200, url

    monkeypatch.setattr(
        "crawl.infrastructure.sources.wenku8_net_source.tls_get", fake_tls
    )
    monkeypatch.setattr(
        "crawl.infrastructure.sources.wenku8_net_source.ocr_image_bytes",
        lambda _b: "OCR line one\nOCR line two",
    )

    text = src.fetch_chapter_content("https://www.wenku8.net/novel/4/4265/175409.htm")
    assert "OCR line one" in text
