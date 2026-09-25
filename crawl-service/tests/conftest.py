"""Chạy TRƯỚC mọi test — đặt DB test riêng, tách khỏi db.sqlite3 thật đang
dùng để dev, để chạy test không bao giờ đụng/xoá dữ liệu thật."""
import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "crawl_service_test.sqlite3"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest  # noqa: E402 (phải set DATABASE_URL trước khi import bất kỳ gì đụng tới app)
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from main import app  # import sau khi đã set DATABASE_URL ở trên

    with TestClient(app) as c:  # context manager -> chạy lifespan (seed data)
        yield c


@pytest.fixture(autouse=True)
def _wait_for_background_threads():
    """Sửa 17/9/2026 — nguyên nhân thật đã xác nhận của vài test order-
    dependent/flaky (`test_fetch_tiers.py::test_browser_fetch_keeps_
    playwright_per_thread`, `test_retry_errors.py::
    test_retry_errors_queues_error_novels`): `client` là session-scoped
    (1 DB SQLite DÙNG CHUNG suốt cả lượt chạy test), nhiều test tự spawn
    thread nền thật (`/run-now`, `/retry`, `/retry-errors`...) rồi return
    NGAY sau khi thấy response 202, không đợi thread đó xong — nếu thread
    đó còn động vào dữ liệu chung (vd `source_key="demo_local"`) khi test
    KHÁC đã bắt đầu chạy, kết quả có thể lẫn lộn tuỳ thứ tự/tốc độ máy chạy
    test. Đợi CHUNG 1 chỗ, SAU MỖI test, tới khi mọi khoá (`crawl-novel:*`/
    `genre-run:*`/`add-novel:*`, `platform_/locks.py`) đã tự nhả — thay vì
    phải tự thêm helper "đợi xong" riêng lẻ vào từng test."""
    yield
    from platform_.locks import wait_until_idle

    wait_until_idle()
