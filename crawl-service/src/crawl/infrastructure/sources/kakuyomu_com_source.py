"""Adapter kakuyomu.jp — web novel Nhật (カクヨム).

Danh sách từ bảng xếp hạng; mục lục + chương tại /works/{id}/episodes/{ep_id}."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_WORK = re.compile(r"^/works/(\d+)$")
_EPISODE = re.compile(r"/works/(\d+)/episodes/(\d+)")


class KakuyomuComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="kakuyomu_com",
                name="Kakuyomu (カクヨム)",
                base_url="https://kakuyomu.jp",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/episodes/"]',
                content_selector=".widget-episodeBody",
                novel_title_selector="h1, .widget-workTitle",
                strip_lines_containing=["kakuyomu.jp", "カクヨム", "応援", "シェア"],
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
        return f"https://kakuyomu.jp/works/{m.group(1)}"

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
        for a in soup.select('a[href^="/works/"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _WORK.match(href)
            if not m:
                continue
            title = (a.get_text(strip=True) or "").strip()
            if not title or len(title) < 2:
                continue
            abs_url = f"https://kakuyomu.jp/works/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        work_m = re.search(r"/works/(\d+)", novel_url)
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
            title = re.sub(r"\d{4}年\d+月\d+日(?:公開)?$", "", a.get_text(strip=True)).strip()
            title = title or f"第{len(chapters) + 1}話"
            abs_url = href if href.startswith("http") else f"https://kakuyomu.jp{href}"
            chapters.append(
                ChapterRef(index=len(chapters) + 1, title=title, url=abs_url)
            )
        if chapters:
            return chapters

        if soup.select_one(self.cfg.content_selector):
            title_node = soup.select_one(self.cfg.novel_title_selector)
            title = title_node.get_text(strip=True) if title_node else "本編"
            return [ChapterRef(index=1, title=title or "本編", url=novel_url.rstrip("/"))]

        raise ScrapeError(
            f"[{self.key}] Không tìm thấy chương tại {novel_url} — site có thể đổi cấu trúc."
        )
