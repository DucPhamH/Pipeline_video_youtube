"""Adapter b.faloo.com (飞卢) — chương miễn phí HTML (`div.noveContent`).
VIP/ảnh OCR bỏ qua (cần login). Tham khảo novel-downloader plugins/sites/faloo."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig
from crawl.infrastructure.sources.content_pipeline import check_fetched_html

_NOVEL_HREF = re.compile(r"(?:https?:)?(?://)?(?:b\.)?faloo\.com/(\d+)\.html", re.I)
_CHAPTER_HREF = re.compile(r"(?:https?:)?(?://)?(?:b\.)?faloo\.com/(\d+)_(\d+)\.html", re.I)


class FalooComSource(BaseHtmlSource):
    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="faloo_com",
                name="faloo.com (飞卢)",
                base_url="https://b.faloo.com",
                genre_item_selector=".TwoBox02_01",
                genre_title_selector="a[href]",
                chapter_list_selector="#mulu a",
                content_selector="div.noveContent",
                novel_title_selector="#novelName, h1",
                strip_lines_containing=["飞卢", "faloo", "本章完"],
                request_delay_sec=1.2,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """Một số bảng xếp hạng (vd đồng nhân) ít `.TwoBox02_01` — gom mọi
        link `/N.html` unique trên trang."""
        if page == 1:
            url = genre_list_url
        elif self.cfg.paginate_list_url is not None:
            url = self.cfg.paginate_list_url(genre_list_url, page)
        else:
            return []
        soup = self._get_soup(url)
        seen: set[str] = set()
        results: list[NovelRef] = []
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            m = _NOVEL_HREF.search(href)
            if not m:
                continue
            book_id = m.group(1)
            if book_id in seen:
                continue
            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            if not title or len(title) < 2:
                continue
            seen.add(book_id)
            results.append(
                NovelRef(
                    title=title,
                    url=f"https://b.faloo.com/{book_id}.html",
                    latest_chapter_title="",
                )
            )
        if not results and page == 1:
            raise ScrapeError(f"[{self.key}] Không tìm thấy truyện tại {url}")
        return results

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        soup = self._get_soup(novel_url)
        m_book = re.search(r"/(\d+)\.html", novel_url)
        book_id = m_book.group(1) if m_book else ""
        box = soup.select_one("#mulu") or soup
        seen: set[str] = set()
        chapters: list[ChapterRef] = []
        for a in box.select("a[href]"):
            href = (a.get("href") or "").strip()
            m = _CHAPTER_HREF.search(href)
            if not m:
                continue
            if book_id and m.group(1) != book_id:
                continue
            key = f"{m.group(1)}_{m.group(2)}"
            if key in seen:
                continue
            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            # Bỏ link "正文" kiểu v_BOOK_N.html (không match _CHAPTER_HREF)
            if not title:
                continue
            seen.add(key)
            chapters.append(
                ChapterRef(
                    index=len(chapters) + 1,
                    title=title,
                    url=f"https://b.faloo.com/{key}.html",
                )
            )
        if not chapters:
            raise ScrapeError(f"[{self.key}] Không tìm thấy chương tại {novel_url}")
        return chapters

    def fetch_chapter_content(self, chapter_url: str) -> str:
        soup = self._get_soup(chapter_url)
        html = str(soup)
        # Sửa 17/9/2026: chỉ tự check 2 cụm cứng bỏ lọt các cách site báo
        # khoá VIP khác wording (site thật có nhiều biến thể, xem
        # content_pipeline._VIP_LOCK_MARKERS) — gọi thêm check DÙNG CHUNG
        # (8 marker đã verify qua nhiều site khác) làm lưới an toàn thứ 2,
        # giữ nguyên 2 cụm riêng của site này vì chưa chắc nằm trong danh
        # sách chung.
        check_fetched_html(html, source_key=self.key, url=chapter_url)
        if "您还没有订阅本章节" in html or "您还没有登录" in html:
            raise ScrapeError(f"[{self.key}] Chương VIP/cần đăng nhập: {chapter_url}")
        node = soup.select_one(self.cfg.content_selector)
        if node is None:
            raise ScrapeError(
                f"[{self.key}] Không tìm thấy nội dung tại {chapter_url}"
            )
        for br in node.find_all("br"):
            br.replace_with("\n")
        lines = [
            line.strip()
            for line in node.get_text("\n").splitlines()
            if line.strip() and not any(bad in line for bad in self.cfg.strip_lines_containing)
        ]
        text = "\n".join(lines)
        if not text:
            raise ScrapeError(f"[{self.key}] Nội dung rỗng tại {chapter_url}")
        return text

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        m = _CHAPTER_HREF.search(chapter_url)
        if not m:
            return None
        return f"https://b.faloo.com/{m.group(1)}.html"

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """y_1.html -> y_1_2.html ; y_1_3.html -> y_1_{page}.html."""
        if page <= 1:
            return url
        m = re.search(r"/y_(\d+)(?:_(\d+))?\.html$", url)
        if m:
            return re.sub(r"/y_\d+(?:_\d+)?\.html$", f"/y_{m.group(1)}_{page}.html", url)
        return url
