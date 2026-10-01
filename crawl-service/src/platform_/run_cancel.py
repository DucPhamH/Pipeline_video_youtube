"""Cờ hủy lượt quét genre đang chạy nền — FE gọi API cancel, scan loop check.

In-process (giống locks.py): đủ cho 1 worker uvicorn. Nhiều worker cần
Redis/DB flag riêng.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from crawl.domain.ports import ScrapeError

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


# --- Cờ dừng theo THREAD — tầng fetch (chờ Retry-After/backoff) kiểm tra
# để không ngủ hàng phút sau khi người dùng đã bấm Dừng quét.
_scope = threading.local()


class CancelledDuringWait(ScrapeError):
    """Đang chờ retry thì lượt quét bị hủy."""


@contextmanager
def cancel_scope(should_stop: Callable[[], bool] | None) -> Iterator[None]:
    prev = getattr(_scope, "should_stop", None)
    _scope.should_stop = should_stop
    try:
        yield
    finally:
        _scope.should_stop = prev


def current_should_stop() -> bool:
    fn = getattr(_scope, "should_stop", None)
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def interruptible_sleep(seconds: float, *, step: float = 0.5) -> None:
    """time.sleep chia nhỏ — raise CancelledDuringWait nếu cờ dừng của
    thread hiện tại bật trong lúc chờ."""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        if current_should_stop():
            raise CancelledDuringWait("Đã hủy trong lúc chờ thử lại")
        left = deadline - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(step, left))
