"""Adapter trxs.cc (同人小说网) — encoding GBK, chương /tongren/{id}/n.html."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig


class TrxsCcSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="trxs_cc",
                name="trxs.cc (同人小说)",
                base_url="https://www.trxs.cc",
                encoding="gbk",
                genre_item_selector="div.bk",
                genre_title_selector="a",
                chapter_list_selector="ul.clearfix a, .book_list a",
                content_selector=".read_chapterDetail",
                strip_lines_containing=["同人小说", "trxs", "作者："],
                paginate_list_url=self._paginate_list_url,
            )
        )

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """Title lấy từ img[alt] — thẻ <a> bọc cả meta nên get_text() bị bẩn."""
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        items = soup.select(self.cfg.genre_item_selector)
        if not items:
            if page == 1:
                raise ScrapeError(
                    f"[{self.key}] Không tìm thấy truyện với selector "
                    f"'{self.cfg.genre_item_selector}' tại {url}"
                )
            return []
        results: list[NovelRef] = []
        for item in items:
            link = item.select_one("a[href]")
            if link is None or not link.get("href"):
                continue
            img = item.select_one("img[alt]")
            title = (img.get("alt") or "").strip() if img else ""
            if not title:
                title = link.get_text(strip=True)
            title = re.split(r"\d+个评分|作者:|MB", title)[0].strip()
            title = re.sub(r"\(.*?\)\s*$", "", title).strip() or title
            if not title:
                continue
            results.append(
                NovelRef(title=title, url=self._abs_url(link["href"]), latest_chapter_title="")
            )
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        anchors = soup.select(self.cfg.chapter_list_selector)
        pat = re.compile(r"/tongren/\d+/\d+\.html")
        seen: set[str] = set()
        chapters: list[ChapterRef] = []
        for a in anchors:
            href = a.get("href") or ""
            if not pat.search(href) or href in seen:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(href)
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=self._abs_url(href))
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {novel_url}")
        return chapters

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        if re.search(r"index_\d+\.html$", url):
            return re.sub(r"index_\d+\.html$", f"index_{page}.html", url)
        if url.endswith("/"):
            return f"{url}index_{page}.html"
        return f"{url.rstrip('/')}/index_{page}.html"
