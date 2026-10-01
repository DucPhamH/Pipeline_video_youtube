"""OpenAICompatTranslator: output cắt cụt (finish_reason=length) phải tự chia,
polish lỗi thì giữ bản dịch, lỗi mạng được retry, backoff dừng được khi
cancel, glossary lớn chỉ gửi thuật ngữ có trong đoạn. Dùng httpx.MockTransport."""
import json
import time

import httpx
import pytest

from translate.infrastructure.providers.openai_compat import (
    OpenAICompatTranslator,
    TranslationCancelled,
)


def _translator(handler, **kwargs) -> OpenAICompatTranslator:
    return OpenAICompatTranslator(
        base_url="https://fake.example/v1",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _reply(text: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": text}, "finish_reason": finish_reason}]}
    )


def _user(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return next(m["content"] for m in body["messages"] if m["role"] == "user")


def _system(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return next(m["content"] for m in body["messages"] if m["role"] == "system")


def test_truncated_output_is_split_instead_of_returned():
    para = "word " * 80  # ~400 ký tự/đoạn
    text = f"{para}\n\n{para}\n\n{para}"

    def handler(request):
        user = _user(request)
        if len(user) > 900:
            return _reply("cut off mid-sente", finish_reason="length")
        return _reply(f"<{len(user)}>")

    out = _translator(handler).translate(text=text, lang_src="en", lang_tgt="vi")
    assert "cut off" not in out
    assert out.count("<") == 2  # đã chia đôi, mỗi nửa dịch riêng


def test_truncated_short_output_raises_never_returns_partial():
    def handler(request):
        return _reply("partial", finish_reason="length")

    with pytest.raises(RuntimeError, match="finish_reason=length"):
        _translator(handler).translate(text="short", lang_src="en", lang_tgt="vi")


def test_polish_failure_keeps_unpolished_translation():
    def handler(request):
        if "Polish wording" in _system(request):
            return httpx.Response(400, text="polish model broken")
        return _reply("bản dịch")

    out = _translator(handler).translate(
        text="Hello", lang_src="en", lang_tgt="vi", mode_params={"polish": True}
    )
    assert out == "bản dịch"


def test_transport_error_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return _reply("ok")

    out = _translator(handler, max_retries=3).translate(text="Hi", lang_src="en", lang_tgt="vi")
    assert out == "ok"
    assert calls["n"] == 2


def test_backoff_sleep_stops_when_job_cancelled():
    def handler(request):
        return httpx.Response(503, text="overloaded")

    t = _translator(handler, max_retries=8)
    t.should_stop = lambda: True
    started = time.time()
    with pytest.raises(TranslationCancelled):
        t.translate(text="Hi", lang_src="en", lang_tgt="vi")
    assert time.time() - started < 2


def test_large_glossary_only_sends_terms_present_in_chunk():
    seen = []

    def handler(request):
        seen.append(_system(request))
        return _reply("ok")

    glossary = [(f"Term{i:02d}", f"T{i}", False) for i in range(60)]
    _translator(handler).translate(
        text="Only Term07 shows up here.", lang_src="en", lang_tgt="vi", glossary=glossary
    )
    assert "Term07 → T7" in seen[0]
    assert "Term08" not in seen[0]

    small = glossary[:5]
    _translator(handler).translate(text="nothing", lang_src="en", lang_tgt="vi", glossary=small)
    assert all(f"Term{i:02d}" in seen[1] for i in range(5))  # glossary nhỏ: giữ nguyên


def test_multi_key_5xx_backs_off_and_retries(monkeypatch):
    from translate.application import run_job as rj
    from translate.application.key_rotator import KeyRotator

    monkeypatch.setattr(rj, "_wait_or_cancelled", lambda seconds, is_cancelled: False)
    req = httpx.Request("POST", "https://fake.example/v1/chat/completions")
    calls = {"n": 0}

    def call(_translator):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.HTTPStatusError(
                "503 from x: busy", request=req, response=httpx.Response(503, request=req)
            )
        return "ok"

    cancelled, out = rj._call_translate_rotating(
        provider="mock",
        base_url="",
        model="m",
        requires_api_key=False,
        keys=["a", "b"],
        rotator=KeyRotator(["a", "b"]),
        is_cancelled=lambda: False,
        translate_call=call,
    )
    assert (cancelled, out) == (False, "ok")
    assert calls["n"] == 3
