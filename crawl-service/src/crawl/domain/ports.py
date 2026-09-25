"""Interface trừu tượng (Protocol) — KHÔNG implement ở đây. application/ chỉ
biết tới các Protocol này, không biết SourcePort thực chạy bằng httpx hay
browser, không biết Repository lưu SQLite hay Postgres."""
from typing import Protocol

from crawl.domain.entities import Chapter, Genre, Novel
from crawl.domain.value_objects import ChapterRef, NovelRef


class ScrapeError(RuntimeError):
    """Lỗi hạ tầng khi crawl: site chặn, đổi cấu trúc, HTTP lỗi..."""


class DuplicateError(RuntimeError):
    """Vi phạm ràng buộc duy nhất (unique constraint) khi 2 thao tác gần
    như đồng thời cùng tạo 1 bản ghi — race condition (vd 2 request bấm
    liên tiếp trước khi request đầu kịp xong). Repository bắt
    `sqlalchemy.exc.IntegrityError` và raise lại thành lỗi domain-friendly
    này, để application/ không phải biết SQLAlchemy là gì (lớp phòng thủ
    thứ 2, phòng khi `platform_.locks.keyed_lock` ở tầng router có kẽ hở —
    vd sau này chạy nhiều worker/instance, in-process lock không còn đủ)."""


class SourcePort(Protocol):
    """1 site nguồn. Implement tầng 1 (httpx BaseHtmlSource), 1b (TLS/
    challenge), hoặc 2 (BaseBrowserSource / Playwright) — xem
    crawl-service.md mục 4c. Use case không biết tầng nào đang chạy."""

    key: str
    name: str
    # True chỉ cho nguồn nội bộ (vd DemoLocalSource) — KHÔNG hiện ở trang
    # "Danh sách site" cho người dùng thật, chỉ dùng test/dry-run (mục 9.0).
    is_test: bool

    def list_genre_novels(self, genre_list_url: str, scan_window: int) -> list[NovelRef]:
        """Top N truyện đầu trang thể loại (đã sort 'mới cập nhật') — dùng
        cho dry-run/preview, xem nhanh 1 trang, không dò thêm."""
        ...

    def list_genre_novels_page(self, genre_list_url: str, page: int) -> list[NovelRef]:
        """TOÀN BỘ truyện ở đúng 1 trang cụ thể (không cắt bớt theo
        scan_window) — dùng cho job quét thật (CrawlGenreUseCase), có thể
        gọi lặp lại với page=2,3,... để dò tiếp khi trang trước bị loại hết
        (mục 7c). Trả [] nếu trang đó không tồn tại/hết truyện — KHÔNG raise
        ScrapeError (chỉ trang 1 rỗng mới là lỗi thật, xem implementation)."""
        ...

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        ...

    def fetch_novel_title(self, novel_url: str) -> str | None:
        """Tiêu đề trang mục lục — dùng khi thêm truyện bằng URL (tránh lưu title=URL).
        Trả None nếu không parse được."""
        ...

    def fetch_chapter_content(self, chapter_url: str) -> str:
        ...

    def derive_novel_url(self, chapter_url: str) -> str | None:
        """Suy ra URL trang mục lục từ URL 1 chương cụ thể — dùng khi người
        dùng dán nhầm/cố ý dán link 1 chương thay vì link mục lục (mục
        'Thêm truyện bằng URL', crawl-service.md mục 9.3).

        Trả None nếu site này KHÔNG suy ra được (chỉ trong site cho phép —
        vd một số site dùng 2 hệ id khác nhau giữa trang mục lục và trang
        chương, không đoán được bằng cách biến đổi URL đơn giản)."""
        ...


class NovelRepository(Protocol):
    def get_by_id(self, novel_id: int) -> Novel | None: ...
    def get_by_source_url(self, source_key: str, source_url: str) -> Novel | None: ...
    def get_by_fingerprint(self, fingerprint: str) -> Novel | None: ...
    def list_all(
        self,
        status: str | None = None,
        source_key: str | None = None,
        search: str | None = None,
        is_manual: bool | None = None,
        genre_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Novel]:
        """`limit=None` trả hết (dùng nội bộ) — router luôn truyền `limit`
        thật để phân trang (mục 9.5). `is_manual` lọc truyện thêm tay vs quét thể loại."""
        ...

    def count_all(
        self,
        status: str | None = None,
        source_key: str | None = None,
        search: str | None = None,
        is_manual: bool | None = None,
        genre_id: int | None = None,
    ) -> int:
        """Tổng số bản ghi khớp filter (KHÔNG áp `limit`/`offset`) — dùng để
        FE tính số trang."""
        ...

    def add(self, novel: Novel) -> Novel: ...
    def update(self, novel: Novel, *, commit: bool = True) -> None: ...
    def delete(self, novel_id: int) -> bool: ...
    def commit(self) -> None: ...


class ChapterRepository(Protocol):
    def get_by_id(self, chapter_id: int) -> Chapter | None: ...
    def list_by_novel(self, novel_id: int) -> list[Chapter]: ...
    def list_by_novel_filtered(
        self,
        novel_id: int,
        *,
        status: str | None = None,
        search: str | None = None,
        reviewed: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Chapter]: ...
    def count_by_novel_filtered(
        self,
        novel_id: int,
        *,
        status: str | None = None,
        search: str | None = None,
        reviewed: bool | None = None,
    ) -> int: ...
    def add(self, chapter: Chapter, *, commit: bool = True) -> Chapter: ...
    def update(self, chapter: Chapter, *, commit: bool = True) -> None: ...
    def delete(self, chapter_id: int) -> bool: ...
    def commit(self) -> None: ...


class GenreRepository(Protocol):
    def get_by_id(self, genre_id: int) -> Genre | None: ...
    def list_enabled(self) -> list[Genre]: ...
    def list_all(self) -> list[Genre]: ...
    def list_by_source_key(self, source_key: str) -> list[Genre]: ...
    def list_filtered(
        self,
        *,
        source_key: str | None = None,
        search: str | None = None,
        enabled: bool | None = None,
        last_run_status: str | None = None,
        allowed_keys: set[tuple[str, str]] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Genre]: ...
    def count_filtered(
        self,
        *,
        source_key: str | None = None,
        search: str | None = None,
        enabled: bool | None = None,
        last_run_status: str | None = None,
        allowed_keys: set[tuple[str, str]] | None = None,
    ) -> int: ...
    def update(self, genre: Genre) -> None: ...
