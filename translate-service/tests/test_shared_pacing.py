"""Giãn cách dùng chung theo (base_url, api_key) — 2 job/thread cùng 1 AI thật
phải tự xếp hàng thay vì bắn song song không kiểm soát; khác AI hoặc mock thì
không bị ảnh hưởng."""
import threading
import time
import uuid

import translate.application.run_job as run_job


def _unique_identity():
    return f"https://fake-{uuid.uuid4().hex}.example/v1", "sk-test"


def test_same_identity_serializes_and_paces(monkeypatch):
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 0.3)
    base_url, api_key = _unique_identity()
    calls: list[float] = []
    lock = threading.Lock()

    def make_call():
        def _call():
            with lock:
                calls.append(time.time())
            return "ok"
        return _call

    results = [None, None]

    def worker(i: int):
        cancelled, out = run_job._call_with_shared_pacing(
            provider="openai",
            base_url=base_url,
            api_key=api_key,
            is_cancelled=lambda: False,
            call=make_call(),
        )
        results[i] = (cancelled, out)

    t1 = threading.Thread(target=worker, args=(0,))
    t2 = threading.Thread(target=worker, args=(1,))
    t1.start()
    time.sleep(0.05)  # đảm bảo t1 giữ khoá/identity trước
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert results[0] == (False, "ok")
    assert results[1] == (False, "ok")
    assert len(calls) == 2
    calls.sort()
    assert calls[1] - calls[0] >= 0.3 - 0.02  # trừ hao sai số scheduler


def test_different_identity_not_throttled_together(monkeypatch):
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 5.0)  # cao để lộ rõ nếu lỡ dùng chung
    base_a, key_a = _unique_identity()
    base_b, key_b = _unique_identity()

    start = time.time()
    cancelled_a, out_a = run_job._call_with_shared_pacing(
        provider="openai", base_url=base_a, api_key=key_a, is_cancelled=lambda: False, call=lambda: "a",
    )
    cancelled_b, out_b = run_job._call_with_shared_pacing(
        provider="openai", base_url=base_b, api_key=key_b, is_cancelled=lambda: False, call=lambda: "b",
    )
    elapsed = time.time() - start

    assert (cancelled_a, out_a) == (False, "a")
    assert (cancelled_b, out_b) == (False, "b")
    assert elapsed < 1.0  # không bị giãn cách chéo giữa 2 identity khác nhau


def test_mock_provider_bypasses_pacing_entirely(monkeypatch):
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 5.0)
    base_url, api_key = _unique_identity()  # cùng identity, nhưng provider=mock

    start = time.time()
    for _ in range(3):
        cancelled, out = run_job._call_with_shared_pacing(
            provider="mock", base_url=base_url, api_key=api_key, is_cancelled=lambda: False, call=lambda: "x",
        )
        assert (cancelled, out) == (False, "x")
    elapsed = time.time() - start
    assert elapsed < 1.0


def test_global_semaphore_caps_concurrent_calls_across_different_identities(monkeypatch):
    """Semaphore toàn cục chặn cả khi 2 lệnh gọi KHÁC identity — không chỉ trùng key."""
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 0.0)
    monkeypatch.setattr(run_job, "_global_call_semaphore", threading.Semaphore(1))
    base_a, key_a = _unique_identity()
    base_b, key_b = _unique_identity()

    in_flight = {"n": 0, "max": 0}
    guard = threading.Lock()

    def make_call(hold: float):
        def _call():
            with guard:
                in_flight["n"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["n"])
            time.sleep(hold)
            with guard:
                in_flight["n"] -= 1
            return "ok"
        return _call

    def worker(base_url, api_key, hold):
        return run_job._call_with_shared_pacing(
            provider="openai", base_url=base_url, api_key=api_key,
            is_cancelled=lambda: False, call=make_call(hold),
        )

    t1 = threading.Thread(target=worker, args=(base_a, key_a, 0.3))
    t2 = threading.Thread(target=worker, args=(base_b, key_b, 0.3))
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Semaphore=1 -> dù khác identity vẫn không được chạy call() đồng thời.
    assert in_flight["max"] == 1


def test_slow_call_does_not_block_next_same_identity_call_from_starting(monkeypatch):
    """Bug thật gặp phải: pool nhiều model CÙNG 1 tài khoản (vd 8 model Gemini
    chung key) — 1 model bị nhà cung cấp báo lỗi tạm thời (503 "high demand")
    tự retry nội bộ ~vài phút bên trong `_chat()`. Nếu khoá identity bị giữ
    suốt lúc `call()` chạy, mọi slot khác CÙNG identity bị chặn đứng chờ, mất
    hết song song thật của pool. Khoá giờ chỉ giữ đủ lâu để giãn cách ĐIỂM BẮT
    ĐẦU, không giữ suốt thời gian `call()` thực thi."""
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 0.1)
    base_url, api_key = _unique_identity()

    call_a_started = threading.Event()
    call_a_may_finish = threading.Event()

    def call_a():
        call_a_started.set()
        call_a_may_finish.wait(timeout=5)
        return "a"

    def call_b():
        return "b"

    results: dict[str, tuple] = {}

    def worker_a():
        results["a"] = run_job._call_with_shared_pacing(
            provider="openai", base_url=base_url, api_key=api_key, is_cancelled=lambda: False, call=call_a,
        )

    t_a = threading.Thread(target=worker_a)
    t_a.start()
    assert call_a_started.wait(timeout=2)  # A đã vào trong call() (giả lập đang tự retry lâu)

    start_b = time.time()
    results["b"] = run_job._call_with_shared_pacing(
        provider="openai", base_url=base_url, api_key=api_key, is_cancelled=lambda: False, call=call_b,
    )
    elapsed_b = time.time() - start_b

    call_a_may_finish.set()
    t_a.join(timeout=5)

    assert results["a"] == (False, "a")
    assert results["b"] == (False, "b")
    # B chỉ phải đợi MIN_CALL_INTERVAL (~0.1s) — KHÔNG phải đợi A "gọi xong"
    # (A lúc này vẫn còn đang treo ở call_a_may_finish, chưa finish).
    assert elapsed_b < 1.0


def test_cancel_while_waiting_for_pacing_returns_no_call(monkeypatch):
    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 2.0)
    base_url, api_key = _unique_identity()
    call_count = {"n": 0}

    def _call():
        call_count["n"] += 1
        return "ok"

    # Lần gọi đầu chiếm identity này
    cancelled, out = run_job._call_with_shared_pacing(
        provider="openai", base_url=base_url, api_key=api_key, is_cancelled=lambda: False, call=_call,
    )
    assert (cancelled, out) == (False, "ok")
    assert call_count["n"] == 1

    # Lần 2 phải chờ MIN_CALL_INTERVAL — cancel ngay lập tức trong lúc chờ
    cancelled2, out2 = run_job._call_with_shared_pacing(
        provider="openai", base_url=base_url, api_key=api_key, is_cancelled=lambda: True, call=_call,
    )
    assert cancelled2 is True
    assert out2 is None
    assert call_count["n"] == 1  # không gọi thêm lần nào
