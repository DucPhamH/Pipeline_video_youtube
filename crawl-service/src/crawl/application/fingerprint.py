"""Fingerprint nội dung — phát hiện truyện trùng (URL khác, cùng sách)."""
from __future__ import annotations

import hashlib
import re


def content_fingerprint(*texts: str, max_chars: int = 4000) -> str:
    """Hash ổn định từ vài đoạn đầu (bỏ whitespace thừa)."""
    chunks: list[str] = []
    budget = max_chars
    for raw in texts:
        if budget <= 0:
            break
        cleaned = re.sub(r"\s+", "", (raw or "").strip())
        if not cleaned:
            continue
        take = cleaned[:budget]
        chunks.append(take)
        budget -= len(take)
    blob = "|".join(chunks).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]
