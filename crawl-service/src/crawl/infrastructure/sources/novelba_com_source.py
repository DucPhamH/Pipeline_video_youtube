"""Adapter novelba.com (ノベルバ) — ranking /indies + mục lục episodes HTML."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_WORK = re.compile(r"/indies/works/(\d+)/?$")
_EPISODE = re.compile(r"/indies/works/(\d+)/episodes/(\d+)")
_UPDATE_SUFFIX = re.compile(r"更新日[：:].*$")


class NovelbaComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="novelba_com",
                name="Novelba (ノベルバ)",
                base_url="https://novelba.com",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/episodes/"]',
                content_selector=".episode_box .detail",
                novel_title_selector="h1",
                strip_lines_containing=["novelba.com", "ノベルバ", "前のエピソード", "次のエピソード"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        if page <= 1:
            return url
        cleaned = re.sub(r"([?&])page=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}page={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _EPISODE.search(chapter_url)
        if not m:
            return None
        return f"https://novelba.com/indies/works/{m.group(1)}"

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
        for a in soup.select('a[href*="/indies/works/"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _WORK.search(href)
            if not m:
                continue
            parent = a.find_parent(["li", "div", "article", "section"])
            title = ""
            if parent is not None:
                title_node = parent.select_one("h2, h3, .title, .work_title")
                if title_node is not None:
                    title = title_node.get_text(strip=True)
            if not title:
                title = (a.get_text(strip=True) or "").strip()
            # Link ranking thường dính rank/genre/tags — lấy dòng tiêu đề sạch nếu có.
            if title and len(title) > 80:
                title_node = parent.select_one("h2, h3, .title") if parent else None
                if title_node is not None:
                    title = title_node.get_text(strip=True)
            if not title or len(title) < 2:
                continue
            abs_url = f"https://novelba.com/indies/works/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        work_m = re.search(r"/indies/works/(\d+)", novel_url)
        work_id = work_m.group(1) if work_m else ""

        chapters: list[ChapterRef] = []
        seen_ep: set[str] = set()
        for a in soup.select('a[href*="/episodes/"]'):
            href = a.get("href") or ""
            m = _EPISODE.search(href)
            if not m or (work_id and m.group(1) != work_id):
                continue
            ep_id = m.group(2)
            if ep_id in seen_ep:
                continue
            seen_ep.add(ep_id)
            title = _UPDATE_SUFFIX.sub("", a.get_text(strip=True)).strip()
            title = title or f"第{len(chapters) + 1}話"
            if title.startswith(("最初から読む", "続きから読む")):
                continue
            abs_url = href if href.startswith("http") else f"https://novelba.com{href}"
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if chapters:
            return chapters
        raise ScrapeError(
            f"[{self.key}] Không tìm thấy chương tại {novel_url} — site có thể đổi cấu trúc."
        )
