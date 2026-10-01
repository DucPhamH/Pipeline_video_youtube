"""Adapter alphapolis.co.jp (アルファポリス) — kế thừa BaseBrowserSource (tầng 2).

Đã verify bằng mạng thật (17/9/2026): MỌI request httpx thuần (kể cả với
nhiều User-Agent khác nhau) lẫn `curl_cffi` TLS-impersonate (chrome136) tới
domain này đều bị AWS WAF trả HTTP 202 kèm header `x-amzn-waf-action:
challenge` và body là trang `challenge.js` (AwsWafIntegration — cần chạy JS
thật để lấy token rồi mới được phục vụ trang thật) — tức đây là JS
challenge THẬT (không phải chỉ soft TLS-fingerprint block), nên tầng 1/1b
CHẮC CHẮN không đủ, phải escalate hẳn lên Playwright (tầng 2). Đã verify
Playwright Chromium headless thật SỰ vượt qua được challenge này (nhận về
HTML đầy đủ ~400KB thay vì trang challenge 2KB).

Thể loại thật (category_ids) lấy từ tag `c-attribute-tag--novel` gắn trên
từng truyện tại trang chủ + trang xếp hạng — đây là link GET thật
`/novel/index?category_ids=<id>` (khác với ranking theo tuần dùng cookie
`novel_hot_rank[hot_rank_genre]` set qua JS `changeGenre()`, KHÔNG dùng
được cho crawler GET thuần nên bỏ qua)."""
import re

from crawl.domain.ports import ScrapeError
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.sources.base_browser_source import BaseBrowserSource
from crawl.infrastructure.sources.base_html_source import SourceConfig

_NOVEL_HREF = re.compile(r"/novel/(\d+)/(\d+)/?$")
_EPISODE_HREF = re.compile(r"/novel/(\d+)/(\d+)/episode/(\d+)/?$")


class AlphapolisCoJpSource(BaseBrowserSource):
    browser_wait_selector = (
        "section.p-content.is-novel, .p-table-of-contents__episode-link, "
        "#novelBody, h1.p-content-info__title"
    )
    prefer_tls_first = False  # đã verify curl_cffi/TLS impersonate KHÔNG qua được AWS WAF — vào thẳng browser

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                key="alphapolis_co_jp",
                name="アルファポリス (Alphapolis)",
                base_url="https://www.alphapolis.co.jp",
                content_locale="ja",
                accept_language="ja,en;q=0.8",
                genre_item_selector="section.p-content.is-novel",
                genre_title_selector="h2.p-content__title a",
                content_selector="#novelBody",
                novel_title_selector="h1.p-content-info__title",
                strip_lines_containing=["アルファポリス", "alphapolis.co.jp"],
                request_delay_sec=1.0,
                paginate_list_url=self._paginate_list_url,
                novel_url_from_chapter=self._derive_novel_url,
            )
        )

    @staticmethod
    def _paginate_list_url(url: str, page: int) -> str:
        """.../novel/index?category_ids=110400 -> ...&page=2 — đã verify
        page=1 vs page=2 trả 2 danh sách truyện khác nhau thật bằng browser
        thật (17/9/2026)."""
        if page <= 1:
            return url
        cleaned = re.sub(r"([?&])page=\d+", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        return f"{cleaned}{sep}page={page}"

    @staticmethod
    def _derive_novel_url(chapter_url: str) -> str | None:
        """.../novel/{authorId}/{novelId}/episode/{episodeId} ->
        .../novel/{authorId}/{novelId} — quy luật ổn định, verify bằng HTML
        thật (17/9/2026)."""
        m = _EPISODE_HREF.search(chapter_url)
        if not m:
            return None
        return f"https://www.alphapolis.co.jp/novel/{m.group(1)}/{m.group(2)}"

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        """Override: tiêu đề chương thật nằm ở div con
        `.p-table-of-contents__episode-title` bên trong thẻ `<a>` (thẻ `<a>`
        còn chứa lượt thích/ngày đăng/số chữ dính liền nếu lấy get_text() cả
        thẻ — đã verify HTML thật 17/9/2026)."""
        soup = self._get_soup(novel_url)
        m = _NOVEL_HREF.search(novel_url)
        if not m:
            raise ScrapeError(
                f"[{self.key}] URL mục lục không đúng định dạng /novel/{{a}}/{{n}}: {novel_url}"
            )
        author_id, novel_id = m.group(1), m.group(2)

        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in soup.select('a.p-table-of-contents__episode-link[href*="/episode/"]'):
            href = a.get("href") or ""
            ep_m = _EPISODE_HREF.search(href)
            if not ep_m or ep_m.group(1) != author_id or ep_m.group(2) != novel_id:
                continue
            ep_id = ep_m.group(3)
            if ep_id in seen:
                continue
            seen.add(ep_id)
            title_node = a.select_one(".p-table-of-contents__episode-title")
            title = (title_node.get_text(strip=True) if title_node else a.get_text(strip=True)) or (
                f"第{len(chapters) + 1}話"
            )
            abs_url = href if href.startswith("http") else f"https://www.alphapolis.co.jp{href}"
            chapters.append(ChapterRef(index=len(chapters) + 1, title=title, url=abs_url))

        if chapters:
            return chapters

        # 短編: nội dung có thể nằm ngay 1 trang duy nhất không qua episode/
        if soup.select_one(self.cfg.content_selector):
            title_node = soup.select_one(self.cfg.novel_title_selector)
            title = title_node.get_text(strip=True) if title_node else "本編"
            return [ChapterRef(index=1, title=title or "本編", url=novel_url.rstrip("/"))]

        raise ScrapeError(
            f"[{self.key}] Không tìm thấy chương tại {novel_url} — site có thể đổi cấu trúc."
        )
