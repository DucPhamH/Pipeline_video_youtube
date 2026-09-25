"""Value object — dataclass bất biến, không có identity/DB row riêng."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ChapterRef:
    """1 dòng trong danh sách chương lấy được từ trang mục lục truyện."""

    index: int
    title: str
    url: str


@dataclass(frozen=True)
class NovelRef:
    """1 dòng trong danh sách truyện lấy được từ trang thể loại."""

    title: str
    url: str  # url trang mục lục chương của truyện
    latest_chapter_title: str  # dùng để soát từ khoá hoàn thành (完本/大结局/...)
