"""Domain entities — thuần Python, có identity (id) nhưng KHÔNG phụ thuộc
SQLAlchemy. Mapping sang ORM nằm ở infrastructure/persistence/repositories.py.
"""
import datetime as dt
import enum
from dataclasses import dataclass, field


class NovelLifecycle(str, enum.Enum):
    """Vòng đời 1 truyện — job hàng ngày chỉ động vào DISCOVERED/CRAWLING,
    bỏ qua mọi trạng thái khác ("Library mode", xem crawl-service.md mục 2)."""

    DISCOVERED = "discovered"
    CRAWLING = "crawling"
    FULLY_CRAWLED = "fully_crawled"
    TRANSLATING = "translating"
    READY_FOR_VIDEO = "ready_for_video"
    PRODUCED = "produced"
    REJECTED = "rejected"  # không khớp tiêu chí ngắn+hoàn thành
    ERROR = "error"


class ChapterStatus(str, enum.Enum):
    PENDING = "pending"
    CRAWLED = "crawled"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class DomainError(Exception):
    """Vi phạm invariant nghiệp vụ (khác lỗi hạ tầng như ScrapeError)."""


class GenreRunStatus(str, enum.Enum):
    """Trạng thái lần quét gần nhất của 1 thể loại — LƯU LẠI (không chỉ giữ
    trong bộ nhớ FE) để bấm "Quét ngay" xong dù có tải lại trang hay quét
    thật chạy rất lâu (nhiều phút, do site chậm/mạng thật) người dùng vẫn
    thấy đúng trạng thái, không tưởng nhầm là không có gì xảy ra."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Genre:
    """1 "option" của 1 site — TẤT CẢ option của cùng 1 site (kể cả bảng
    xếp hạng chung như "Hot nhất") nằm CHUNG 1 danh sách PHẲNG, chỉ ĐÚNG 1
    option "active" tại 1 thời điểm (SetActiveGenreUseCase, nhóm theo
    `source_key`) — sửa 17/9/2026 (2 lần):
    (1) bỏ hẳn khái niệm "kind" (từng tách UI thành 2 select box "Thể
        loại"/"Xếp hạng" riêng) theo phản hồi thật "sao vẫn chia làm 2
        block" — muốn ĐÚNG 1 card/site.
    (2) bỏ tiếp khái niệm "family_key"/"is_hot_variant" (từng ghép 1 thể
        loại + biến thể "Hot nhất" của nó thành 1 khối "Thể loại" + select
        con "Sắp xếp") theo phản hồi thật "dựa vào menu của site ý, mỗi
        site nó độc lập đó, ko tự tạo thêm menu cho select" — mỗi URL liệt
        kê/xếp hạng có thật trên site (kể cả bản "Hot nhất" riêng theo từng
        thể loại) giờ là 1 DÒNG ĐỘC LẬP, PHẲNG trong CHÍNH select "Thể
        loại", không gộp cặp, không sinh thêm select nào khác — đúng 1
        select duy nhất mirror thẳng danh sách các trang thật của site."""

    id: int | None
    source_key: str
    genre_key: str
    label: str
    list_url: str
    enabled: bool = True
    last_run_status: GenreRunStatus = GenreRunStatus.IDLE
    last_run_started_at: dt.datetime | None = None
    last_run_finished_at: dt.datetime | None = None
    last_run_discovered: int | None = None
    last_run_rejected: int | None = None
    last_run_errors: int | None = None
    last_run_messages: str | None = None

    def mark_run_started(self) -> None:
        self.last_run_status = GenreRunStatus.RUNNING
        self.last_run_started_at = dt.datetime.utcnow()
        self.last_run_finished_at = None

    def mark_run_finished(
        self, *, status: GenreRunStatus, discovered: int, rejected: int, errors: int, messages: list[str]
    ) -> None:
        """`status=DONE` khi chạy xong bình thường (có thể vẫn có lỗi lẻ tẻ
        từng truyện, xem `errors`), `status=ERROR` chỉ dùng khi cả lượt quét
        crash ngoài dự kiến (bug/exception, không phải lỗi 1 site/truyện)."""
        self.last_run_status = status
        self.last_run_finished_at = dt.datetime.utcnow()
        self.last_run_discovered = discovered
        self.last_run_rejected = rejected
        self.last_run_errors = errors
        self.last_run_messages = "\n".join(messages) if messages else None


@dataclass
class Chapter:
    id: int | None
    novel_id: int
    chapter_index: int
    title: str
    source_url: str
    raw_path: str | None = None
    status: ChapterStatus = ChapterStatus.PENDING
    error_message: str | None = None
    queued_for_translate: bool = False
    # Đã có người xem/sửa nội dung raw chưa — crawl về mà không đọc/sửa được
    # thì vô dụng, nên cần theo dõi việc này (mục "review chương").
    reviewed: bool = False
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)

    def mark_crawled(self, raw_path: str) -> None:
        self.raw_path = raw_path
        self.status = ChapterStatus.CRAWLED
        self.queued_for_translate = True
        self.error_message = None

    def mark_reviewed(self) -> None:
        """Gọi khi người dùng lưu lại nội dung đã xem/sửa (mục
        UpdateChapterContentUseCase)."""
        self.reviewed = True

    def mark_failed(self, reason: str) -> None:
        self.status = ChapterStatus.FAILED
        self.error_message = reason


@dataclass
class Novel:
    id: int | None
    title: str
    source_key: str
    source_url: str
    genre_id: int | None = None
    is_manual: bool = False
    last_chapter_index: int = 0
    is_complete: bool = False
    total_chapters: int | None = None
    lifecycle_status: NovelLifecycle = NovelLifecycle.DISCOVERED
    error_message: str | None = None
    author: str = ""
    cover_url: str = ""
    content_fingerprint: str = ""
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime | None = None

    def start_crawling(self) -> None:
        if self.lifecycle_status not in (NovelLifecycle.DISCOVERED, NovelLifecycle.ERROR):
            raise DomainError(
                f"Không thể crawl novel {self.id} đang ở trạng thái {self.lifecycle_status}"
            )
        self.lifecycle_status = NovelLifecycle.CRAWLING
        self.error_message = None

    def start_incremental_crawl(self) -> None:
        """Crawl thêm chương mới cho truyện đã có — site đẩy truyện lên đầu
        danh sách khi ra chương mới (quét lần 2+)."""
        if self.lifecycle_status in (NovelLifecycle.FULLY_CRAWLED, NovelLifecycle.ERROR):
            self.lifecycle_status = NovelLifecycle.CRAWLING
            self.error_message = None
            return
        if self.lifecycle_status == NovelLifecycle.DISCOVERED:
            self.start_crawling()
            return
        raise DomainError(
            f"Không thể crawl bổ sung novel {self.id} đang ở trạng thái {self.lifecycle_status}"
        )

    def advance_chapter(self, chapter_index: int) -> None:
        """Gọi ngay sau khi 1 chương crawl xong — cho phép resume nếu lỗi giữa chừng."""
        self.last_chapter_index = max(self.last_chapter_index, chapter_index)

    def mark_fully_crawled(self) -> None:
        self.lifecycle_status = NovelLifecycle.FULLY_CRAWLED

    def mark_translating(self) -> None:
        if self.lifecycle_status not in (
            NovelLifecycle.FULLY_CRAWLED,
            NovelLifecycle.ERROR,
            NovelLifecycle.TRANSLATING,
            NovelLifecycle.READY_FOR_VIDEO,
        ):
            raise DomainError(
                f"Không thể gửi dịch novel {self.id} đang ở trạng thái {self.lifecycle_status}"
            )
        self.lifecycle_status = NovelLifecycle.TRANSLATING
        self.error_message = None

    def mark_ready_for_video(self) -> None:
        if self.lifecycle_status not in (
            NovelLifecycle.TRANSLATING,
            NovelLifecycle.READY_FOR_VIDEO,
            NovelLifecycle.FULLY_CRAWLED,
        ):
            raise DomainError(
                f"Không thể đánh dấu ready_for_video novel {self.id} "
                f"(hiện: {self.lifecycle_status})"
            )
        self.lifecycle_status = NovelLifecycle.READY_FOR_VIDEO
        self.error_message = None

    def mark_translate_failed(self, reason: str) -> None:
        """Dịch lỗi — giữ ở translating kèm message, hoặc quay fully_crawled nếu chưa bắt đầu."""
        if self.lifecycle_status == NovelLifecycle.TRANSLATING:
            self.error_message = reason
            return
        if self.lifecycle_status in (NovelLifecycle.FULLY_CRAWLED, NovelLifecycle.READY_FOR_VIDEO):
            self.lifecycle_status = NovelLifecycle.FULLY_CRAWLED
            self.error_message = reason
            return
        raise DomainError(
            f"Không ghi lỗi dịch cho novel {self.id} (hiện: {self.lifecycle_status})"
        )

    def mark_error(self, reason: str) -> None:
        self.lifecycle_status = NovelLifecycle.ERROR
        self.error_message = reason

    def reject(self, reason: str) -> None:
        self.lifecycle_status = NovelLifecycle.REJECTED
        self.error_message = reason

    def force_accept(self) -> None:
        """Bỏ qua tiêu chí ngắn+hoàn thành (mục 9.5 UI 'Buộc nhận')."""
        if self.lifecycle_status != NovelLifecycle.REJECTED:
            raise DomainError("Chỉ force-accept được novel đang ở trạng thái rejected")
        self.lifecycle_status = NovelLifecycle.DISCOVERED
        self.error_message = None
