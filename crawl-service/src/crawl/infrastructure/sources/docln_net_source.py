"""Adapter docln.net / hako — light novel dịch VN; thường cần CRAWL_PROXY_VN.

Selectors theo lncrawl `sources/vi/lnhakone.py`. Chương có thể cần login.
"""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class DoclnNetSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="docln_net",
                name="DocLN / Hako (docln.net · cần proxy VN)",
                base_url="https://docln.net",
                content_locale="vi",
                accept_language="vi,en;q=0.8",
                genre_item_selector=".sect-body .thumb-item-flow, .thumb-item-flow",
                genre_title_selector=".series-title a",
                chapter_list_selector=".list-chapters a, .volume-list .list-chapters a",
                content_selector="#chapter-content, .chapter-content",
                novel_title_selector=".series-name a, h1, .series-name",
                novel_author_selector='.info-value a[href*="/tac-gia/"]',
                novel_cover_selector=".series-cover .img-in-ratio, .series-cover img",
                strip_lines_containing=["docln", "hako", "bình luận", "Đăng nhập"],
                request_delay_sec=1.2,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        # .../truyen/123-slug/c456-chuong -> .../truyen/123-slug
        m = re.match(r"^(https?://[^/]+/truyen/[^/]+)/c\d+", chapter_url, re.I)
        return m.group(1) if m else None

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        sep = "&" if "?" in url else "?"
        if re.search(r"[?&]page=\d+", url):
            return re.sub(r"([?&])page=\d+", rf"\1page={page}", url)
        return f"{url}{sep}page={page}"

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select(self.cfg.chapter_list_selector):
            href = a.get("href") or ""
            if not href or "/c" not in href:
                continue
            abs_url = self._abs_url(href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không có chương tại {novel_url} — "
                "cần CRAWL_PROXY_VN hoặc cookie đăng nhập."
            )
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Thiếu #chapter-content tại {chapter_url} — "
                "chương khoá / cần đăng nhập."
            )
        paras = [
            p.get_text("\n", strip=True)
            for p in node.select("p")
            if p.get_text(strip=True)
        ]
        text = "\n".join(paras) if paras else node.get_text("\n", strip=True)
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip()
            and not any(bad in ln for bad in self.cfg.strip_lines_containing)
        ]
        if len("\n".join(lines)) < 80:
            raise ScrapeError(
                f"[{self.key}] Nội dung quá ngắn (có thể cần login) tại {chapter_url}"
            )
        return "\n".join(lines)
