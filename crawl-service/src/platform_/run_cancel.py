"""Cờ hủy lượt quét genre đang chạy nền — FE gọi API cancel, scan loop check.

In-process (giống locks.py): đủ cho 1 worker uvicorn. Nhiều worker cần
Redis/DB flag riêng.
"""
from __future__ import annotations

import threading

_guard = threading.Lock()
_flags: dict[int, threading.Event] = {}


def begin_run(genre_id: int) -> None:
    """Gọi lúc bắt đầu execute. Giữ Event đã set nếu cancel tới sớm hơn thread."""
    with _guard:
        existing = _flags.get(genre_id)
        if existing is not None and existing.is_set():
            return
        _flags[genre_id] = threading.Event()


def end_run(genre_id: int) -> None:
    with _guard:
        _flags.pop(genre_id, None)


def request_cancel(genre_id: int) -> bool:
    """Set cờ hủy. Tạo Event nếu chưa có (race: cancel trước begin_run)."""
    with _guard:
        ev = _flags.get(genre_id)
        if ev is None:
            ev = threading.Event()
            _flags[genre_id] = ev
        ev.set()
        return True


def is_cancelled(genre_id: int) -> bool:
    with _guard:
        ev = _flags.get(genre_id)
        return bool(ev is not None and ev.is_set())
