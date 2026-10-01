from tts.application.pieces import chunk_text, split_roles
from tts.application.voices import static_voices
from tts.infrastructure.engines.edge import ssml_with_style


class _Cfg:
    voice = "Microsoft Server Speech Text to Speech Voice (zh-CN, XiaoxiaoNeural)"
    pitch = "+0Hz"
    rate = "+0%"
    volume = "+0%"


def test_quotes_become_dialogue_and_narration():
    parts = split_roles('Anh nói "đi đi" rồi im.', dialogue=True)
    assert [role for role, _text in parts] == ["narrator", "dialogue", "narrator"]
    assert parts[1][1] == "đi đi"

    cn = split_roles("他说「走吧」便离开。", dialogue=True)
    assert ("dialogue", "走吧") in cn


def test_no_dialogue_voice_keeps_one_narration():
    parts = split_roles('Anh nói "đi đi".', dialogue=False)
    assert parts == [("narrator", 'Anh nói "đi đi".')]


def test_long_text_is_split():
    text = " ".join(["câu này đủ dài để ghép."] * 40)
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 500 for c in chunks)


def test_static_catalog_has_two_vietnamese_and_more_chinese():
    vi = static_voices("vi")
    zh = static_voices("zh")
    assert {v.id for v in vi} == {"vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"}
    assert len(zh) > 2
    xiao = next(v for v in zh if v.id == "zh-CN-XiaoxiaoNeural")
    assert "story" in xiao.styles


def test_style_ssml_uses_express_as():
    ssml = ssml_with_style(_Cfg(), "hello", "cheerful")
    assert "mstts:express-as" in ssml
    assert "style='cheerful'" in ssml
    plain = ssml_with_style(_Cfg(), "hello", "")
    assert "express-as" not in plain
