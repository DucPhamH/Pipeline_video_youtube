"""Lưu snapshot tiến độ crawl đang chạy — FE poll qua API.

Key: `genre:{id}` / `novel:{id}` (cùng task_id trong CrawlProgress).
In-memory, mất khi restart process — chỉ phục vụ UI live, không thay last_run_*.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, replace

from crawl.application.progress import CrawlProgress

_lock = threading.RLock()
_latest: dict[str, CrawlProgress] = {}


def publish(progress: CrawlProgress) -> None:
    with _lock:
        _latest[progress.task_id] = replace(progress)


def get(task_id: str) -> CrawlProgress | None:
    with _lock:
        p = _latest.get(task_id)
        return replace(p) if p is not None else None


def get_genre(genre_id: int) -> CrawlProgress | None:
    return get(f"genre:{genre_id}")


def clear(task_id: str) -> None:
    with _lock:
        _latest.pop(task_id, None)


def as_api_dict(progress: CrawlProgress | None) -> dict | None:
    if progress is None:
        return None
    return asdict(progress)
