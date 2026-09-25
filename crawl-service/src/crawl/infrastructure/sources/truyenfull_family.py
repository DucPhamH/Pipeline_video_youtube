"""Họ CMS TruyenFull (HTML + phân trang /trang-N/).

`.live` thường mở được từ IP ngoài VN; `.today` / `.vn` / `.vision` hay
bị reset TCP — cần `CRAWL_PROXY_VN` (exit Việt Nam).
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_CHAPTER_PAGE = re.compile(r"/trang-(\d+)/?", re.I)


class TruyenfullFamilySource(BaseHtmlSource):
    """Template chung — subclass chỉ đổi key/name/base_url (+ optional ajax)."""

    use_ajax_chapter_list = False

    def __init__(self, *, key: str, name: str, base_url: str) -> None:
        host = base_url.rstrip("/").split("//", 1)[-1]
        super().__init__(
            SourceConfig(
                key=key,
                name=name,
                base_url=base_url.rstrip("/"),
                content_locale="vi",
                accept_language="vi,en;q=0.8",
                genre_item_selector=".list-truyen .row[itemtype], .list-truyen .row",
                genre_title_selector="h3.truyen-title a, .truyen-title a",
                genre_latest_chapter_selector=".chapter-text, .author",
                chapter_list_selector="ul.list-chapter li a, #list-chapter li a, .list-chapter li a",
                content_selector="#chapter-c, .chapter-c",
                novel_title_selector="h3.title, h1.title, .col-truyen-header h3",
                novel_author_selector='.info a[itemprop="author"]',
                novel_cover_selector=".books .book img, .book-thumb img, [itemprop='image']",
                strip_lines_containing=[
                    "truyenfull",
                    "TruyenFull",
                    host,
                    "quảng cáo",
                    "bình luận",
                    "Bình luận",
                ],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = re.match(r"^(https?://[^/]+/.+?/)chuong-\d+/?", chapter_url, re.I)
        return m.group(1) if m else None

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        base = url.rstrip("/")
        if re.search(r"/trang-\d+/?$", base):
            return re.sub(r"/trang-\d+/?$", f"/trang-{page}/", base)
        return f"{base}/trang-{page}/"

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        if self.use_ajax_chapter_list:
            ajax = self._list_chapters_ajax(novel_url)
            if ajax:
                return ajax
        return self._list_chapters_html_pages(novel_url)

    def _list_chapters_html_pages(self, novel_url: str) -> list[ChapterRef]:
        base = novel_url.split("#")[0].rstrip("/")
        if _CHAPTER_PAGE.search(base):
            base = re.sub(r"/trang-\d+/?$", "", base)

        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        max_page = 1
        page = 1
        while page <= max_page and page <= 40:
            url = base if page == 1 else f"{base}/trang-{page}/"
            soup = self._get_soup(url)
            for a in soup.select(self.cfg.chapter_list_selector):
                href = a.get("href") or ""
                if not href:
                    continue
                abs_url = self._abs_url(href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                chapters.append(
                    ChapterRef(
                        index=len(chapters) + 1,
                        title=a.get_text(strip=True) or (a.get("title") or "").strip(),
                        url=abs_url,
                    )
                )
            for a in soup.select(".pagination a[href], ul.pagination a[href]"):
                href = a.get("href") or ""
                m = _CHAPTER_PAGE.search(href)
                if m:
                    max_page = max(max_page, int(m.group(1)))
            page += 1

        if not chapters:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy chương tại {novel_url} — "
                "cần CRAWL_PROXY_VN (exit VN) hoặc site đổi cấu trúc."
            )
        return chapters

    def _list_chapters_ajax(self, novel_url: str) -> list[ChapterRef] | None:
        """Giống lncrawl: POST-less GET ajax.php?type=list_chapter (truyenfull.today)."""
        soup = self._get_soup(novel_url)
        tid = soup.select_one("input#truyen-id")
        total = soup.select_one("input#total-page")
        ascii_ = soup.select_one("input#truyen-ascii")
        title_node = soup.select_one(self.cfg.novel_title_selector)
        if not tid or not total or not ascii_ or not title_node:
            return None
        try:
            total_page = int((total.get("value") or "0").strip())
        except ValueError:
            return None
        if total_page < 1:
            return None

        novel_title = title_node.get_text(strip=True)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for page in range(1, min(total_page, 40) + 1):
            params = urlencode(
                {
                    "type": "list_chapter",
                    "tid": (tid.get("value") or "").strip(),
                    "tascii": (ascii_.get("value") or "").strip(),
                    "tname": novel_title,
                    "page": page,
                    "totalp": total_page,
                }
            )
            ajax_url = f"{self.cfg.base_url}/ajax.php?{params}"
            self._apply_user_session()
            resp = self._client.get(ajax_url, headers={"Referer": novel_url})
            if resp.status_code != 200:
                raise ScrapeError(f"[{self.key}] ajax HTTP {resp.status_code} {ajax_url}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ScrapeError(f"[{self.key}] ajax JSON lỗi: {exc}") from exc
            frag = payload.get("chap_list") or ""
            frag_soup = BeautifulSoup(frag, "lxml")
            for a in frag_soup.select(".list-chapter a, ul.list-chapter li a"):
                href = a.get("href") or ""
                if not href:
                    continue
                abs_url = self._abs_url(href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                title = (a.get("title") or a.get_text(strip=True) or "").strip()
                chapters.append(
                    ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
                )
        return chapters or None
