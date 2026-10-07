"""Adapter truyendichfull.site — thay MeTruyenCV (đã đóng cửa 10/02/2026).

List thể loại HTML; mục lục + chương qua path UUID trong SSR Next.js.
"""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_UUID = re.compile(
    r"/truyen/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))?",
    re.I,
)


class TruyendichfullSiteSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="truyendichfull_site",
                name="TruyenDichFull (thay MeTruyenCV · đã đóng)",
                base_url="https://truyendichfull.site",
                content_locale="vi",
                accept_language="vi,en;q=0.8",
                genre_item_selector='a[href*="/truyen/"]',
                genre_title_selector='a[href*="/truyen/"]',
                chapter_list_selector="unused",
                content_selector=".tiptap-reader",
                novel_title_selector="h1",
                strip_lines_containing=[
                    "truyendichfull",
                    "Truyện Dich Full",
                    "quảng cáo",
                    "Bản dịch",
                ],
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
        m = _UUID.search(chapter_url)
        if not m:
            return None
        return f"https://truyendichfull.site/truyen/{m.group(1)}"

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
        for a in soup.select('a[href*="/truyen/"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _UUID.search(href)
            if not m or m.group(2):
                continue
            title = a.get_text(" ", strip=True)
            # Bỏ prefix stats kiểu "127chương435đọc..." (không có khoảng trắng).
            title = re.sub(
                r"^(?:\d+chương\d*đọc|\d+\s*chương\s*\d*\s*đọc)?(?:FULL)?",
                "",
                title,
                flags=re.I,
            ).strip()
            if len(title) < 2:
                # fallback: lấy từ img alt / aria
                img = a.select_one("img[alt]")
                title = (img.get("alt") if img else "") or title
            title = title.strip()
            if len(title) < 2:
                continue
            abs_url = f"https://truyendichfull.site/truyen/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        html = str(soup)
        novel_m = _UUID.search(novel_url)
        if not novel_m:
            raise ScrapeError(f"[{self.key}] URL truyện không hợp lệ: {novel_url}")
        novel_id = novel_m.group(1)
        paths = re.findall(
            rf"/truyen/{novel_id}/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-"
            rf"[0-9a-f]{{4}}-[0-9a-f]{{12}})",
            html,
            re.I,
        )
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for chap_id in paths:
            if chap_id in seen:
                continue
            seen.add(chap_id)
            abs_url = f"https://truyendichfull.site/truyen/{novel_id}/{chap_id}"
            chapters.append(
                ChapterRef(
                    index=len(chapters) + 1,
                    title=f"Chương {len(chapters) + 1}",
                    url=abs_url,
                )
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không thấy chương tại {novel_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(".tiptap-reader") or soup.select_one(".text-reader")
        if node is None:
            raise ScrapeError(f"[{self.key}] Thiếu nội dung tại {chapter_url}")
        text = node.get_text("\n", strip=True)
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip()
            and not any(bad.lower() in ln.lower() for bad in self.cfg.strip_lines_containing)
        ]
        body = "\n".join(lines)
        if len(body) < 80:
            raise ScrapeError(f"[{self.key}] Nội dung quá ngắn tại {chapter_url}")
        return body
