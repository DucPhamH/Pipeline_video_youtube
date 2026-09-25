"""Ước token / USD trước khi chạy job — heuristic, không gọi provider."""
from __future__ import annotations

# CJK / Latin rough chars-per-token (OpenAI-ish heuristics).
_CJK_LANGS = {"zh", "ja", "ko", "zh-cn", "zh-tw", "zh-hans", "zh-hant"}


def _chars_per_token(text: str, *, lang_src: str) -> float:
    lang = (lang_src or "").strip().lower()
    if lang in _CJK_LANGS or any("一" <= c <= "鿿" for c in text[:200]):
        return 1.5
    return 4.0


def estimate_tokens(text: str, *, lang_src: str) -> int:
    chars = len(text or "")
    if chars == 0:
        return 0
    per = _chars_per_token(text, lang_src=lang_src)
    input_tok = max(1, int(chars / per))
    # Input + output roughly 2× cho 1 pass dịch/adapt (output ~ dài bằng input)
    return input_tok * 2


def estimate_beats_pass_tokens(text: str, *, lang_src: str) -> int:
    """audio_cut chạy THÊM 1 pass trích must_keep_beats trước khi condense
    (spec 4.3) — input đọc cả chương, output chỉ 1 outline ngắn (không nhân
    đôi như estimate_tokens, vì output pass này không dài bằng input)."""
    chars = len(text or "")
    if chars == 0:
        return 0
    per = _chars_per_token(text, lang_src=lang_src)
    return max(1, int(chars / per)) + 300


def estimate_usd(tokens: int, *, usd_per_1k: float) -> float:
    if tokens <= 0 or usd_per_1k <= 0:
        return 0.0
    return round((tokens / 1000.0) * usd_per_1k, 6)
