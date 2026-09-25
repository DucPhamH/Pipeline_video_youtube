"""Test platform_/locks.py — cơ chế chặn 2 yêu cầu cùng key chạy chồng lên
nhau (dùng ở router cho run-now/add-novel/retry/force-accept)."""
import pytest

from platform_.locks import AlreadyRunningError, keyed_lock


def test_second_lock_on_same_key_raises_immediately():
    with keyed_lock("k1"):
        with pytest.raises(AlreadyRunningError):
            with keyed_lock("k1"):
                pass  # không bao giờ chạy tới đây


def test_lock_released_after_with_block_exits():
    with keyed_lock("k2"):
        pass
    # Phải lấy lại được key này sau khi block trước đã thoát — không bị
    # "kẹt" lock mãi mãi.
    with keyed_lock("k2"):
        pass


def test_different_keys_do_not_block_each_other():
    with keyed_lock("k3-a"):
        with keyed_lock("k3-b"):
            pass  # không raise


def test_lock_released_even_when_body_raises():
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with keyed_lock("k4"):
            raise _Boom("lỗi giả lập trong lúc giữ khoá")

    # Khoá phải được nhả (finally) dù thân with raise lỗi.
    with keyed_lock("k4"):
        pass
