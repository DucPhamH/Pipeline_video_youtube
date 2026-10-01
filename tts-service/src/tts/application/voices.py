"""Catalog giọng. Edge kéo danh sách sống; lỗi mạng thì dùng bảng tĩnh."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import edge_tts

SAMPLE = {
    "vi": "Xin chào, đây là giọng đọc thử.",
    "zh": "你好，这是试听。",
    "en": "Hello, this is a voice preview.",
}

DEFAULT_VOICE = {
    "vi": "vi-VN-HoaiMyNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-AriaNeural",
}


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    label: str
    locale: str
    gender: str
    styles: tuple[str, ...] = ()


# Style của giọng Trung lấy từ catalog Azure/Edge (Xiaoxiao, Yunxi). Tiếng Việt chỉ có 2 giọng neural.
STATIC: tuple[VoiceInfo, ...] = (
    VoiceInfo("vi-VN-HoaiMyNeural", "HoaiMy", "vi-VN", "Female"),
    VoiceInfo("vi-VN-NamMinhNeural", "NamMinh", "vi-VN", "Male"),
    VoiceInfo(
        "zh-CN-XiaoxiaoNeural",
        "Xiaoxiao",
        "zh-CN",
        "Female",
        ("calm", "cheerful", "newscast", "poetry-reading", "sad", "story"),
    ),
    VoiceInfo(
        "zh-CN-YunxiNeural",
        "Yunxi",
        "zh-CN",
        "Male",
        ("narration-relaxed", "cheerful", "newscast", "serious", "sad"),
    ),
    VoiceInfo("zh-CN-XiaoyiNeural", "Xiaoyi", "zh-CN", "Female", ("cheerful", "gentle", "sad")),
    VoiceInfo("zh-CN-YunjianNeural", "Yunjian", "zh-CN", "Male"),
    VoiceInfo("zh-HK-HiuMaanNeural", "HiuMaan", "zh-HK", "Female"),
    VoiceInfo("zh-TW-HsiaoChenNeural", "HsiaoChen", "zh-TW", "Female"),
    VoiceInfo("en-US-AriaNeural", "Aria", "en-US", "Female", ("newscast", "cheerful", "sad")),
    VoiceInfo("en-US-GuyNeural", "Guy", "en-US", "Male", ("newscast", "cheerful")),
    VoiceInfo("en-US-JennyNeural", "Jenny", "en-US", "Female"),
    VoiceInfo("en-GB-SoniaNeural", "Sonia", "en-GB", "Female"),
)

_STYLES = {v.id: v.styles for v in STATIC if v.styles}


@dataclass(frozen=True)
class Preset:
    id: str
    voice: str
    dialogue_voice: str
    rate: str
    pitch: str
    volume: str
    style: str
    lang: str


PRESETS: tuple[Preset, ...] = (
    Preset("nu_ke_cham", "vi-VN-HoaiMyNeural", "", "-15%", "+0Hz", "+0%", "", "vi"),
    Preset("nam_ke", "vi-VN-NamMinhNeural", "", "+0%", "+0Hz", "+0%", "", "vi"),
    Preset("doi_thoai", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "+0%", "+0Hz", "+0%", "", "vi"),
    Preset("nu_ke_cham", "zh-CN-XiaoxiaoNeural", "", "-10%", "+0Hz", "+0%", "story", "zh"),
    Preset("nam_ke", "zh-CN-YunxiNeural", "", "+0%", "+0Hz", "+0%", "narration-relaxed", "zh"),
    Preset("doi_thoai", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "+0%", "+0Hz", "+0%", "", "zh"),
    Preset("nu_ke_cham", "en-US-AriaNeural", "", "-10%", "+0Hz", "+0%", "", "en"),
    Preset("nam_ke", "en-US-GuyNeural", "", "+0%", "+0Hz", "+0%", "", "en"),
    Preset("doi_thoai", "en-US-AriaNeural", "en-US-GuyNeural", "+0%", "+0Hz", "+0%", "", "en"),
)


def lang_primary(lang: str) -> str:
    return (lang or "").strip().lower().replace("_", "-").split("-")[0]


def lang_matches(locale: str, lang: str) -> bool:
    primary = lang_primary(lang)
    if not primary:
        return True
    loc = (locale or "").lower()
    return loc == primary or loc.startswith(primary + "-")


def sample_for(lang: str) -> str:
    return SAMPLE.get(lang_primary(lang), SAMPLE["en"])


def default_voice(lang: str) -> str:
    return DEFAULT_VOICE.get(lang_primary(lang), DEFAULT_VOICE["en"])


def static_voices(lang: str) -> list[VoiceInfo]:
    return [v for v in STATIC if lang_matches(v.locale, lang)]


def presets_for(lang: str) -> list[Preset]:
    primary = lang_primary(lang) or "vi"
    found = [p for p in PRESETS if p.lang == primary]
    return found or [p for p in PRESETS if p.lang == "vi"]


async def list_voices(engine: str, lang: str) -> list[VoiceInfo]:
    if engine == "vieneu":
        from tts.infrastructure.engines.vieneu import list_presets

        return [
            VoiceInfo(voice_id, label, "vi-VN", gender)
            for voice_id, label, gender in list_presets()
        ]
    if engine != "edge":
        return static_voices(lang)
    try:
        live = await asyncio.wait_for(edge_tts.list_voices(), timeout=3)
    except Exception:  # noqa: BLE001 — catalog tĩnh khi Edge không trả lời
        return static_voices(lang)
    out: list[VoiceInfo] = []
    for row in live:
        short = str(row.get("ShortName") or "")
        locale = str(row.get("Locale") or "")
        if not short or not lang_matches(locale, lang):
            continue
        out.append(
            VoiceInfo(
                id=short,
                label=str(row.get("FriendlyName") or row.get("DisplayName") or short),
                locale=locale,
                gender=str(row.get("Gender") or ""),
                styles=_STYLES.get(short, ()),
            )
        )
    return out or static_voices(lang)
