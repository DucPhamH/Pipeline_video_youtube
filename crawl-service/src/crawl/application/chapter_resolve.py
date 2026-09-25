"""Helper dùng chung — lấy mục lục chương linh hoạt (mọi site)."""
from __future__ import annotations

from crawl.domain.ports import ScrapeError, SourcePort
from crawl.domain.value_objects import ChapterRef


def try_list_chapters(source: SourcePort, url: str) -> tuple[list[ChapterRef] | None, str | None]:
    """Thử `list_chapters(url)`; fail thì thử URL mục lục suy ra từ 1 chương."""
    try:
        return source.list_chapters(url), None
    except ScrapeError as first_error:
        derived = source.derive_novel_url(url)
        if derived is None or derived == url:
            return None, str(first_error)
        try:
            return source.list_chapters(derived), None
        except ScrapeError as second_error:
            return None, f"{first_error}; thử mục lục suy ra ({derived}): {second_error}"
