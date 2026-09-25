"""OpenAICompatTranslator — already_translated wording + audio_cut 2-pass
(must_keep_beats trước khi cắt, spec 4.3). Dùng httpx.MockTransport — không gọi
mạng thật."""
import json

import httpx

from translate.infrastructure.providers.openai_compat import OpenAICompatTranslator


def _translator(handler, **kwargs) -> OpenAICompatTranslator:
    return OpenAICompatTranslator(
        base_url="https://fake.example/v1",
        api_key="test-key",
        model="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
    )


def test_full_mode_says_translate_not_already_translated():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return _reply("bản dịch")

    t = _translator(handler)
    out = t.translate(
        text="Hello world",
        lang_src="en",
        lang_tgt="vi",
        mode="full",
        already_translated=False,
    )
    assert out == "bản dịch"
    assert len(calls) == 1  # full: đúng 1 pass, không có beats-extraction
    system = calls[0]["messages"][0]["content"]
    assert "Translate the user's chapter from en to vi" in system
    assert "already in" not in system


def test_forked_pov_says_already_translated_no_translate_verb():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return _reply("đã đổi ngôi")

    t = _translator(handler)
    out = t.translate(
        text="Bản dịch tiếng Việt rồi",
        lang_src="vi",
        lang_tgt="vi",
        mode="pov",
        mode_params={"target_pov": "first_person"},
        already_translated=True,
    )
    assert out == "đã đổi ngôi"
    assert len(calls) == 1  # pov không phải audio_cut -> vẫn 1 pass
    system = calls[0]["messages"][0]["content"]
    assert "already in vi" in system
    assert "do NOT translate it further" in system
    assert "Translate the user's chapter from" not in system
    assert "first person" in system


def test_audio_cut_does_beats_extraction_pass_then_condense():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return _reply("- Hero finds the sword\n- Villain reveals identity")
        return _reply("bản rút gọn")

    t = _translator(handler)
    out = t.translate(
        text="Chương dài...",
        lang_src="vi",
        lang_tgt="vi",
        mode="audio_cut",
        mode_params={"target_minutes": 5, "max_chars": 800, "keep_dialogue_ratio": 0.7},
        already_translated=True,
    )
    assert out == "bản rút gọn"
    assert len(calls) == 2  # (1) must_keep_beats  (2) condense có beats

    beats_system = calls[0]["messages"][0]["content"]
    assert "MUST-KEEP BEATS" in beats_system  # prompt trích beats, đúng vai trò pass 1

    condense_system = calls[1]["messages"][0]["content"]
    assert "MUST-KEEP BEATS (preserve all, in order):" in condense_system
    assert "Hero finds the sword" in condense_system  # beats từ pass 1 được đưa vào pass 2
    assert "already in vi" in condense_system


def test_title_never_leaks_into_user_message():
    """Bug thật gặp phải: nhét 'Title: X' vào user message khiến 1 số model
    (Groq qwen…) hiểu nhầm là nội dung cần dịch rồi in lại 'Tiêu đề: X' vào đầu
    output — lệch format so với model khác cùng job. Title giờ chỉ nằm trong
    system prompt làm ngữ cảnh, không bao giờ vào user message."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return _reply("bản dịch")

    t = _translator(handler)
    t.translate(
        text="Nội dung chương.",
        lang_src="en",
        lang_tgt="vi",
        title="Chương 1: Khởi đầu",
        mode="full",
    )
    user_msg = calls[0]["messages"][1]["content"]
    system_msg = calls[0]["messages"][0]["content"]
    assert user_msg == "Nội dung chương."  # tuyệt đối không kèm "Title: ..."
    assert "Title:" not in user_msg
    assert "Chương 1: Khởi đầu" in system_msg  # vẫn có làm ngữ cảnh, chỉ khác chỗ
    assert "do NOT output this line" in system_msg


def test_empty_content_is_retried_not_marked_success():
    """Bug thật gặp phải: model (reasoning model như qwen3, deepseek-r1-distill)
    thỉnh thoảng trả content rỗng (cắt cụt giữa lúc "suy nghĩ") — code cũ trả
    thẳng chuỗi rỗng, segment bị đánh dấu DONE mà không có bản dịch thật. Giờ
    coi content rỗng là lỗi tạm thời, tự thử lại."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return _reply("")  # lần đầu model trả rỗng
        return _reply("bản dịch thật")

    t = _translator(handler, max_retries=3)
    out = t.translate(text="abc", lang_src="en", lang_tgt="vi", mode="full")
    assert out == "bản dịch thật"
    assert len(calls) == 2


def test_empty_content_forever_raises_after_max_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return _reply("")

    t = _translator(handler, max_retries=2)
    try:
        t.translate(text="abc", lang_src="en", lang_tgt="vi", mode="full")
        assert False, "phải raise khi model luôn trả rỗng"
    except RuntimeError as exc:
        assert "rỗng" in str(exc)
