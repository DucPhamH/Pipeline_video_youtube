"""Adapter piaotia.com (飘天文学) — list booksort*, catalog /html/.../index.html,
nội dung cần normalize HTML gãy (GetFont/GetMode). Tham khảo novel-downloader
plugins/sites/piaotia. Đã verify mạng thật."""
import re
import time

from bs4 import BeautifulSoup

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import check_fetched_html

_BOOKINFO = re.compile(r"/bookinfo/(\d+)/(\d+)\.html?", re.I)


class PiaotiaComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="piaotia_com",
                name="piaotia.com (飘天文学)",
                base_url="https://www.piaotia.com",
                encoding="gbk",
                genre_item_selector="tr",
                genre_title_selector="td.odd a",
                chapter_list_selector="div.centent a",
                content_selector="#content",
                novel_title_selector="h1",
                novel_author_selector="",
                novel_cover_selector="",
                strip_lines_containing=["飘天", "piaotia", "上一章", "下一章", "返回目录", "返回书页"],
                request_delay_sec=1.2,
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
        results: list[NovelRef] = []
        seen: set[str] = set()
        for row in soup.select(self.cfg.genre_item_selector):
            link = row.select_one(self.cfg.genre_title_selector)
            if link is None or not link.get("href"):
                continue
            href = link["href"]
            if not _BOOKINFO.search(href):
                continue
            title = link.get_text(strip=True)
            if not title:
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
        catalog_url = self._catalog_url(novel_url)
        if not catalog_url:
            raise ScrapeError(f"[{self.key}] Không suy ra mục lục từ {novel_url}")
        soup = self._get_soup(catalog_url)
        anchors = soup.select(self.cfg.chapter_list_selector)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in anchors:
            href = (a.get("href") or "").strip()
            if not href.endswith(".html") or href in seen:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(href)
            # chapter href relative to catalog dir
            if href.startswith("http"):
                chapter_url = href
            else:
                base = catalog_url.rsplit("/", 1)[0] + "/"
                chapter_url = base + href.lstrip("/")
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=chapter_url)
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {catalog_url}")
        return chapters

    def fetch_novel_title(self, novel_url: str) -> str | None:
        soup = self._get_soup(novel_url)
        node = soup.select_one("span h1, h1")
        if node is None:
            return None
        title = node.get_text(strip=True)
        return title or None

    def _extract_raw_page_text(self, chapter_url: str) -> str:
        """HTML piaotia gãy — thay script GetMode/GetFont bằng div thật rồi parse."""
        self._apply_user_session()
        headers = {"Referer": self.cfg.base_url}
        if getattr(self, "_session_cookie_header", ""):
            headers["Cookie"] = self._session_cookie_header
        try:
            resp = self._client.get(chapter_url, headers=headers)
        except Exception as exc:
            raise ScrapeError(f"[{self.key}] Lỗi mạng {chapter_url}: {exc}") from exc
        if resp.status_code != 200:
            raise ScrapeError(f"[{self.key}] HTTP {resp.status_code} tại {chapter_url}")
        raw = resp.content.decode(self.cfg.encoding or "gbk", errors="ignore")
        check_fetched_html(raw, source_key=self.key, url=chapter_url)
        raw = (
            raw.replace("<head>", "")
            .replace("</head>", "")
            .replace("<body>", "")
            .replace("</body>", "")
            .replace(
                '<script language="javascript">GetMode();</script>',
                '<div id="main" class="colors1 sidebar">',
            )
            .replace(
                '<script language="javascript">GetFont();</script>',
                '<div id="content">',
            )
        )
        soup = BeautifulSoup(raw, "lxml")
        node = soup.select_one("#content")
        if node is None:
            raise ScrapeError(f"[{self.key}] Không tìm thấy #content tại {chapter_url}")
        for br in node.find_all("br"):
            br.replace_with("\n")
        for bad in node.select("h1, div.toplink, table"):
            bad.decompose()
        time.sleep(self.cfg.request_delay_sec)
        return node.get_text("\n")

    @staticmethod
    def _catalog_url(novel_url: str) -> str | None:
        m = _BOOKINFO.search(novel_url)
        if not m:
            return None
        return f"https://www.piaotia.com/html/{m.group(1)}/{m.group(2)}/index.html"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        # /html/16/16386/799.html -> bookinfo
        m = re.search(r"/html/(\d+)/(\d+)/", chapter_url)
        if not m:
            return None
        return f"https://www.piaotia.com/bookinfo/{m.group(1)}/{m.group(2)}.html"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """/booksort7/0/1.html -> /booksort7/0/{page}.html"""
        if page <= 1:
            return url
        if re.search(r"/\d+\.html$", url):
            return re.sub(r"/\d+\.html$", f"/{page}.html", url)
        return url
