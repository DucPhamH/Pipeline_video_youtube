"""OpenCC 繁简 — dùng `opencc-python-reimplemented` (phổ biến, không cần binary hệ thống)."""
from __future__ import annotations

# mode setting → OpenCC config name
OPENCC_MODES: dict[str, str] = {
    "none": "",
    "t2s": "t2s",  # 繁 → 简
    "s2t": "s2t",  # 简 → 繁
    "s2tw": "s2tw",  # 简 → 台灣正體
    "tw2s": "tw2s",  # 台灣 → 简
}


def apply_opencc(text: str, mode: str | None) -> str:
    key = (mode or "none").strip().lower()
    cfg = OPENCC_MODES.get(key, "")
    if not cfg or not text:
        return text
    try:
        from opencc import OpenCC
    except ImportError:
        return text
    try:
        return OpenCC(cfg).convert(text)
    except Exception:
        return text
