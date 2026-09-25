"""Adapter novel.daysneo.com (NOVEL DAYS / Kodansha) — ranking + /works/episode HTML."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_WORK = re.compile(r"/works/([0-9a-f]+)\.html$", re.I)
_EPISODE = re.compile(r"/works/episode/([0-9a-f]+)\.html$", re.I)


class DaysneoComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="daysneo_com",
                name="NOVEL DAYS (novel.daysneo.com)",
                base_url="https://novel.daysneo.com",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/works/episode/"]',
                content_selector=".episode .inner",
                novel_title_selector="h1",
                strip_lines_containing=["daysneo.com", "NOVEL DAYS", "文字数", "次のエピソード"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        cleaned = re.sub(r"([?&])page=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}page={page}"

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
        for a in soup.select('a[href*="/works/"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _WORK.search(href)
            if not m:
                continue
            title = (a.get_text(strip=True) or "").strip()
            if not title or len(title) < 2:
                continue
            abs_url = f"https://novel.daysneo.com/works/{m.group(1)}.html"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/works/episode/"]'):
            href = a.get("href") or ""
            m = _EPISODE.search(href.split("?")[0])
            if not m:
                continue
            ep_id = m.group(1).lower()
            if ep_id in seen:
                continue
            seen.add(ep_id)
            title = (a.get_text(strip=True) or "").strip()
            title = re.sub(r"公開日\s*:\s*\d{4}/\d{2}/\d{2}$", "", title).strip()
            title = title or f"第{len(chapters) + 1}話"
            if title.startswith("1話目から読む"):
                continue
            abs_url = href if href.startswith("http") else f"https://novel.daysneo.com{href}"
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if chapters:
            return chapters
        raise ScrapeError(
            f"[{self.key}] Không tìm thấy chương tại {novel_url} — site có thể đổi cấu trúc."
        )
