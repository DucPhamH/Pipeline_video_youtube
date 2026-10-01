"""Parse JSON array model trả về (hay kèm ``` fence hoặc vài chữ thừa)."""
from __future__ import annotations

import json


def parse_json_array(raw: str) -> list:
    """Trả list; raise ValueError nếu không tìm được mảng JSON hợp lệ."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            raise ValueError("Model không trả về mảng JSON") from None
        try:
            data = json.loads(text[start : end + 1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Model trả về JSON hỏng") from exc
    if not isinstance(data, list):
        raise ValueError("Model không trả về mảng JSON")
    return data
