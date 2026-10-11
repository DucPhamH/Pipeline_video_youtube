"""Adapter novema.jp (ノベマ！) — UGC JP; thay Hameln (syosetu.org bị Cloudflare).

Ranking theo genre + sách tại /book/n{id}/{ep}.
"""
from __future__ import annotations

import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig

_BOOK = re.compile(r"/book/(n\d+)(?:/(\d+))?/?$")


class NovemaJpSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="novema_jp",
                name="Novema (novema.jp · thay Hameln/CF)",
                base_url="https://novema.jp",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="unused",
                genre_title_selector="unused",
                chapter_list_selector='a[href*="/book/n"]',
                content_selector="article",
                novel_title_selector="h1",
                strip_lines_containing=["novema.jp", "ノベマ", "応援", "ランキング"],
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
        m = _BOOK.search(chapter_url)
        if not m:
            return None
        return f"https://novema.jp/book/{m.group(1)}"

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
        for a in soup.select('a[href*="/book/n"]'):
            href = (a.get("href") or "").split("?")[0]
            m = _BOOK.search(href)
            if not m or m.group(2):
                continue
            title = a.get_text(strip=True)
            if len(title) < 2:
                continue
            abs_url = f"https://novema.jp/book/{m.group(1)}"
            if abs_url in seen:
                continue
            seen.add(abs_url)
            results.append(NovelRef(title=title, url=abs_url, latest_chapter_title=""))
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không parse được sách tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        book_m = _BOOK.search(novel_url)
        book_id = book_m.group(1) if book_m else ""
        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/book/n"]'):
            href = a.get("href") or ""
            m = _BOOK.search(href)
            if not m or not m.group(2):
                continue
            if book_id and m.group(1) != book_id:
                continue
            ep = m.group(2)
            if ep in seen:
                continue
            seen.add(ep)
            title = a.get_text(strip=True)
            if title in {"読む", "続きを読む"}:
                continue
            abs_url = href if href.startswith("http") else f"https://novema.jp{href}"
            chapters.append(
                ChapterRef(
                    index=len(chapters) + 1,
                    title=title or f"第{ep}話",
                    url=abs_url,
                )
            )
        chapters.sort(
            key=lambda c: int(m.group(2)) if (m := _BOOK.search(c.url)) and m.group(2) else c.index
        )
        chapters = [
            ChapterRef(index=i, title=ch.title, url=ch.url)
            for i, ch in enumerate(chapters, start=1)
        ]
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không thấy chương tại {novel_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url, check_content_blockers=True)
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(f"[{self.key}] Thiếu article tại {chapter_url}")
        # Nhiều trang Novema để text ngoài <p> (br / text node) — ưu tiên full article.
        paras = [
            p.get_text("\n", strip=True)
            for p in node.select("p")
            if p.get_text(strip=True)
        ]
        para_text = "\n".join(paras)
        full_text = node.get_text("\n", strip=True)
        text = full_text if len(full_text) > len(para_text) + 40 else (para_text or full_text)
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip()
            and not any(bad in ln for bad in self.cfg.strip_lines_containing)
        ]
        # bỏ header kiểu "1 / 35"
        if lines and re.match(r"^\d+\s*/\s*\d+$", lines[0]):
            lines = lines[1:]
        body = "\n".join(lines)
        if len(body) < 80:
            raise ScrapeError(f"[{self.key}] Nội dung quá ngắn tại {chapter_url}")
        return body
