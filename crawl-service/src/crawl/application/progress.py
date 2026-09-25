"""Sự kiện tiến độ crawl — use case emit, terminal UI / log / FE subscribe."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class CrawlProgress:
    """Snapshot 1 task (genre scan hoặc crawl 1 novel)."""

    task_id: str
    kind: str  # "genre" | "novel"
    label: str
    phase: str  # listing | evaluating | crawling | done | error | cancelled
    page: int = 0
    max_pages: int = 0
    discovered: int = 0
    rejected: int = 0
    errors: int = 0
    synced: int = 0
    scan_window: int = 0
    novel_title: str = ""
    chapter_index: int = 0
    chapter_total: int = 0
    message: str = ""


ProgressCallback = Callable[[CrawlProgress], None]


class ProgressReporter(Protocol):
    def __call__(self, progress: CrawlProgress) -> None: ...


def noop_progress(_progress: CrawlProgress) -> None:
    return None
