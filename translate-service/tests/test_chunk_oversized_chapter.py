"""Chương quá to so với hạn mức TPM/OTPM per-request của model (bug thật user
gặp — xem CHANGELOG) — kiểu AiNiee: thử gửi cả chương trước, CHỈ khi provider
báo lỗi "request quá to" mới tự cắt đôi theo đoạn văn và thử lại từng nửa, ghép
kết quả lại. Không tự cắt sẵn theo 1 ngưỡng cố định, không cắt vì lỗi khác."""
import json

import httpx

from translate.infrastructure.providers.openai_compat import OpenAICompatTranslator


def _translator(handler) -> OpenAICompatTranslator:
    return OpenAICompatTranslator(
        base_url="https://fake.example/v1",
        api_key="test-key",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )


def test_oversized_chapter_auto_splits_and_joins_with_local_context():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_msg = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
        system_msg = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
        calls.append(user_msg)
        if len(user_msg) > 500:  # dưới ngưỡng chia nhỏ tối thiểu (_MIN_SPLITTABLE_CHARS=500)
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": (
                            "Request too large for model `test-model` on tokens per "
                            "minute (TPM): please reduce your message size and try again."
                        )
                    }
                },
            )
        marker = "[SEEN-LOCAL-CTX] " if "STORY CONTEXT" in system_msg else ""
        return httpx.Response(200, json={"choices": [{"message": {"content": f"{marker}TR:{user_msg}"}}]})

    t = _translator(handler)
    para1 = "A" * 300
    para2 = "B" * 300
    text = f"{para1}\n\n{para2}"  # tổng 602 ký tự (>500 -> fail nguyên cụm); mỗi nửa 300 (<=500 -> OK)
    out = t.translate(text=text, lang_src="en", lang_tgt="vi", mode="full")

    # 1 lần thử nguyên cụm (fail, quá to) + 2 lần dịch từng nửa = 3 lệnh gọi.
    assert len(calls) == 3
    assert calls[0] == text  # lần đầu thử NGUYÊN CỤM, không tự cắt trước
    assert f"TR:{para1}" in out
    assert f"TR:{para2}" in out
    assert out.index(f"TR:{para1}") < out.index(f"TR:{para2}")  # đúng thứ tự, không đảo
    # Nửa sau (para2) phải thấy đuôi nửa trước (para1) làm ngữ cảnh cục bộ.
    assert "[SEEN-LOCAL-CTX]" in out


def test_non_size_error_does_not_trigger_splitting():
    """Lỗi khác (vd model không tồn tại) KHÔNG được tự cắt nhỏ thử lại — cắt
    nhỏ không giải quyết được lỗi kiểu này, chỉ tổ tốn thêm lệnh gọi vô ích."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404, json={"error": {"message": "The model `x` does not exist"}})

    t = _translator(handler)
    para1 = "A" * 300
    para2 = "B" * 300
    text = f"{para1}\n\n{para2}"
    try:
        t.translate(text=text, lang_src="en", lang_tgt="vi", mode="full")
        assert False, "phải raise, không được âm thầm trả rỗng"
    except Exception as exc:  # noqa: BLE001
        assert "does not exist" in str(exc)
    assert len(calls) == 1  # không tự cắt thử lại


def test_split_recurses_when_first_half_still_too_large():
    """1 nửa vẫn quá to thì tiếp tục cắt đôi nửa đó — đệ quy, không chỉ cắt 1 lần."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_msg = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
        calls.append(user_msg)
        if len(user_msg) > 500:
            return httpx.Response(
                400,
                json={"error": {"message": "Request too large: reduce your message size and try again."}},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": f"TR:{user_msg}"}}]})

    t = _translator(handler)
    p1, p2, p3, p4 = ("A" * 300, "B" * 300, "C" * 300, "D" * 300)
    # Tổng 1206 ký tự -> fail; cắt đôi còn 2 mảnh 602 ký tự -> VẪN fail (>500)
    # -> phải cắt đệ quy tiếp thành 4 mảnh 300 ký tự mới OK.
    text = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"
    out = t.translate(text=text, lang_src="en", lang_tgt="vi", mode="full")

    for p in (p1, p2, p3, p4):
        assert f"TR:{p}" in out
    # thứ tự đúng, không đảo lộn giữa các mảnh
    positions = [out.index(f"TR:{p}") for p in (p1, p2, p3, p4)]
    assert positions == sorted(positions)
