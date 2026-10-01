"""DTO cho use case — dataclass thuần, KHÔNG phải Pydantic (Pydantic chỉ ở
tầng api/schemas.py)."""
from dataclasses import dataclass, field


@dataclass
class CrawlGenreResult:
    genre_id: int
    discovered: int = 0
    synced: int = 0  # truyện đã có, bổ sung chương mới (site đẩy lên đầu list)
    rejected: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)
    # True khi dừng sớm vì site chết / lỗi liên tiếp — FE báo error, không "done".
    stopped_as_error: bool = False
    # True khi người dùng bấm Dừng quét.
    cancelled: bool = False


@dataclass
class CrawlNovelResult:
    novel_id: int
    chapters_crawled: int
    success: bool
    error: str | None = None
    cancelled: bool = False

    @classmethod
    def failure(
        cls,
        novel_id: int,
        error: str,
        chapters_crawled: int = 0,
        *,
        cancelled: bool = False,
    ) -> "CrawlNovelResult":
        """Rút gọn các chỗ trả lỗi trong use_cases.py — tránh lặp lại
        `success=False` + đủ 4 field mỗi lần."""
        return cls(
            novel_id=novel_id,
            chapters_crawled=chapters_crawled,
            success=False,
            error=error,
            cancelled=cancelled,
        )


@dataclass
class ChapterContentResult:
    chapter_id: int
    success: bool
    content: str | None = None
    reviewed: bool = False
    error: str | None = None
    has_cleaned: bool = False
    content_source: str = "raw"  # "raw" | "cleaned"
    raw_content: str | None = None
    cleaned_content: str | None = None

    @classmethod
    def failure(cls, chapter_id: int, error: str) -> "ChapterContentResult":
        return cls(chapter_id=chapter_id, success=False, error=error)


@dataclass
class ChapterRetryResult:
    """Kết quả "Crawl lại" ĐÚNG 1 chương lỗi (mục 9.6 crawl-service.md) —
    khác `CrawlNovelResult` (crawl lại nguyên truyện)."""

    chapter_id: int
    success: bool
    status: str  # ChapterStatus sau khi retry ("crawled"/"failed"/"unsupported")
    error: str | None = None
    # True nếu đây là chương THIẾU CUỐI CÙNG — truyện vừa chuyển đủ 100%
    # chương, ghi chú "Thiếu N chương" (mục 9.2b) đã được xoá theo.
    novel_completed: bool = False

    @classmethod
    def failure(cls, chapter_id: int, error: str, status: str = "failed") -> "ChapterRetryResult":
        return cls(chapter_id=chapter_id, success=False, status=status, error=error)


@dataclass
class SmoothNovelResult:
    novel_id: int
    success: bool
    chapters_smoothed: int = 0
    chapters_skipped: int = 0
    # Số chương bị bỏ qua vì đã review/sửa tay (không có force) — nằm trong chapters_skipped.
    chapters_protected: int = 0
    removed_lines: int = 0
    chapter_ids: list[int] = field(default_factory=list)
    error: str | None = None


@dataclass
class DeleteResult:
    success: bool
    error: str | None = None


@dataclass
class NovelExportStatus:
    crawled: int = 0
    cleaned: int = 0
    reviewed: int = 0
    can_export_workbook: bool = False
    can_export_txt: bool = False
    can_export_epub: bool = False
    can_export_bundle: bool = False


@dataclass
class ReviewAllResult:
    success: bool
    chapters_reviewed: int = 0
    chapters_skipped: int = 0
    error: str | None = None


@dataclass
class DryRunResult:
    ok: bool
    mode: str
    preview: list[dict] | None = None   # mode="chapters"
    content_preview: str | None = None  # mode="content"
    content_length: int | None = None
    validation_passed: bool | None = None
    error: str | None = None
