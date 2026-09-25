"""In-process lock theo key — chặn 2 yêu cầu cùng thao tác 1 entity cùng
lúc (vd bấm "Quét ngay"/"Thêm truyện"/"Thử lại" 2 lần liên tiếp trước khi
lần đầu kịp xong, hoặc job lịch chạy trùng lúc người dùng bấm tay).

CHỈ hiệu quả trong 1 process — nếu sau này chạy nhiều worker/instance, lock
này KHÔNG đủ (mỗi worker có bộ nhớ riêng), cần thay bằng lock ở tầng DB
(advisory lock của Postgres, hoặc 1 bảng "locks" riêng). Ghi chú lại đây để
không ai tưởng nhầm đã an toàn tuyệt đối.
"""
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()  # bảo vệ việc tạo Lock mới trong _locks khỏi tự race


class AlreadyRunningError(RuntimeError):
    """Đã có 1 yêu cầu giống hệt đang xử lý dở — dùng để báo lỗi rõ ràng
    ngay lập tức thay vì để 2 yêu cầu chạy chồng lên nhau (dẫn tới
    IntegrityError khi cả 2 cùng insert 1 bản ghi)."""


@contextmanager
def keyed_lock(key: str):
    """Không chờ (non-blocking) — nếu key đang bị giữ, raise ngay
    AlreadyRunningError thay vì block request thứ 2 (crawl có thể mất khá
    lâu, block sẽ dễ timeout phía client)."""
    if not try_acquire(key):
        raise AlreadyRunningError(f"Đang có yêu cầu khác xử lý '{key}', vui lòng đợi rồi thử lại")
    try:
        yield
    finally:
        release(key)


def try_acquire(key: str) -> bool:
    """Bản "rời" của keyed_lock — dùng khi phần việc thật sự chạy ở 1 thread
    NỀN khác (vd endpoint trả response ngay, giao việc cho thread nền), nên
    không gói gọn trong 1 khối `with` được. Nhớ gọi `release(key)` khi thread
    nền xong việc (kể cả khi lỗi — dùng try/finally)."""
    with _locks_guard:
        lock = _locks[key]
    return lock.acquire(blocking=False)


def release(key: str) -> None:
    with _locks_guard:
        lock = _locks.get(key)
    if lock is not None and lock.locked():
        lock.release()


def any_locked() -> bool:
    """Có khoá nào (bất kỳ key nào) đang bị giữ hay không — dùng để chờ mọi
    thread nền THẬT SỰ đã xong việc, không chỉ đợi response HTTP trả về
    (202 chỉ nghĩa là ĐÃ BẮT ĐẦU chạy nền, không phải đã xong)."""
    with _locks_guard:
        locks = list(_locks.values())
    return any(lock.locked() for lock in locks)


def wait_until_idle(timeout: float = 3.0) -> None:
    """Đợi tới khi KHÔNG còn khoá nào bị giữ (mọi thread nền đã tự
    `release()` xong) hoặc hết `timeout` — dùng ở test để tránh 1 test kết
    thúc trong khi thread nền do chính nó khởi tạo vẫn còn chạy dở, làm
    nhiễu DB dùng chung sang test SAU (sửa 17/9/2026, xem
    `tests/conftest.py`). KHÔNG dùng trong code sản phẩm thật — chỉ hợp lý
    cho test vì block đợi không giới hạn là điều production code cố tránh."""
    deadline = time.time() + timeout
    while any_locked() and time.time() < deadline:
        time.sleep(0.02)
