"""Adapter wenku8.net (轻小说文库) — tầng 1b curl_cffi; CF nặng → Playwright.
List thể loại thường cần cookie đăng nhập. Book/catalog/chapter free OK qua TLS.
Tham khảo novel-downloader plugins/sites/wenku8.
"""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_browser_source import BaseBrowserSource
from crawl.infrastructure.sources.base_html_source import SourceConfig
from crawl.infrastructure.sources.content_pipeline import (
    assert_not_vip_locked,
    ocr_image_bytes,
)
from crawl.infrastructure.sources.tls_fetch import tls_get

_BOOK = re.compile(r"/book/(\d+)\.htm", re.I)
_CHAPTER = re.compile(r"/novel/\d+/(\d+)/(\d+)\.htm", re.I)


class Wenku8NetSource(BaseBrowserSource):
    browser_wait_selector = "#content, table.css, a[href*='/book/']"
    prefer_tls_first = True
    # wenku8 catalog/book/chapter ổn qua curl_cffi — không cần Playwright (tránh chậm + lỗi thread nền)
    tls_only: bool = True

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="wenku8_net",
                name="wenku8.net (轻小说文库)",
                base_url="https://www.wenku8.net",
                encoding="gbk",
                genre_item_selector="div#content table tr",
                genre_title_selector='a[href*="/book/"]',
                chapter_list_selector="td.ccss a",
                content_selector="#content",
                novel_title_selector="table b, #title, h1",
                strip_lines_containing=["轻小说文库", "wenku8", "返回书页", "上一页", "下一页"],
                request_delay_sec=2.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        html = str(soup)
        if "login.php" in html and "/book/" not in html:
            raise ScrapeError(
                f"[{self.key}] Danh sách yêu cầu cookie đăng nhập wenku8 — "
                f"dán session trên trang site. URL: {url}"
            )
        results: list[NovelRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/book/"]'):
            href = a.get("href") or ""
            m = _BOOK.search(href)
            if not m:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 2:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        m = _BOOK.search(novel_url)
        if not m:
            raise ScrapeError(f"[{self.key}] URL book không hợp lệ: {novel_url}")
        book_id = m.group(1)
        prefix = "0" if len(book_id) <= 3 else book_id[:-3]
        catalog_url = f"https://www.wenku8.net/novel/{prefix}/{book_id}/index.htm"
        soup = self._get_soup(catalog_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select(self.cfg.chapter_list_selector):
            href = (a.get("href") or "").strip()
            title = a.get_text(strip=True)
            if not href.endswith(".htm") or not title:
                continue
            if href.startswith("http"):
                chapter_url = href
            else:
                chapter_url = f"https://www.wenku8.net/novel/{prefix}/{book_id}/{href.lstrip('/')}"
            if chapter_url in seen:
                continue
            seen.add(chapter_url)
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=chapter_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {catalog_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url)
        assert_not_vip_locked(str(soup), source_key=self.key, url=chapter_url)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(f"[{self.key}] Không tìm thấy #content tại {chapter_url}")
        image_urls = self._collect_chapter_image_urls(node)
        for bad in node.select("ul#contentdp, div.divimage"):
            bad.decompose()
        text = self._extract_text_lines(node)
        if not text and image_urls:
            text = self._ocr_chapter_images(image_urls, referer=chapter_url)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng tại {chapter_url}")
        return text

    def _extract_text_lines(self, node) -> str:
        for br in node.find_all("br"):
            br.replace_with("\n")
        lines = [
            line.strip()
            for line in node.get_text("\n").splitlines()
            if line.strip()
            and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        return "\n".join(lines)

    @staticmethod
    def _collect_chapter_image_urls(node) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for img in node.select("div.divimage img, img.imagecontent"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src or src in seen:
                continue
            seen.add(src)
            if src.startswith("//"):
                src = "https:" + src
            urls.append(src)
        return urls

    def _ocr_chapter_images(self, image_urls: list[str], *, referer: str) -> str:
        cookie = getattr(self, "_session_cookie_header", "") or ""
        parts: list[str] = []
        for img_url in image_urls:
            status, body, _ = tls_get(
                img_url,
                cookie_header=cookie,
                referer=referer or self.cfg.base_url,
                source_key=self.key,
                proxy=getattr(self, "_proxy_url", None) or None,
            )
            if status != 200 or len(body) < 100:
                raise ScrapeError(
                    f"[{self.key}] Không tải ảnh chương HTTP {status}: {img_url}"
                )
            parts.append(ocr_image_bytes(body))
        return "\n\n".join(parts)

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("http"):
            return href
        return super()._abs_url(href)

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER.search(chapter_url)
        if not m:
            return None
        return f"https://www.wenku8.net/book/{m.group(1)}.htm"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if "page=" in url:
            return re.sub(r"page=\d+", f"page={page}", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page}"
