"""Xoay vòng API key cùng 1 model — kiểu AiNiee/Glossarion.

- Round-robin mỗi lần lấy key (chia tải giữa nhiều tài khoản).
- Cooldown ngắn khi key bị rate-limit → tự nhảy sang key khác thay vì
  đốt hết retry trên cùng 1 key (vượt pattern "chỉ chia slot chương").
"""
from __future__ import annotations

import threading
import time


def looks_rate_limited(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "429" in msg:
        return True
    needles = (
        "rate limit",
        "rate_limit",
        "too many requests",
        "quota exceeded",
        "resource_exhausted",
        "exceeded your current quota",
    )
    return any(n in msg for n in needles)


class KeyRotator:
    def __init__(self, keys: list[str] | None):
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in keys or []:
            k = (raw or "").strip()
            if k and k not in seen:
                cleaned.append(k)
                seen.add(k)
        self._keys = cleaned or [""]
        self._idx = 0
        self._lock = threading.Lock()
        self._cooldown_until: dict[str, float] = {}

    @property
    def keys(self) -> list[str]:
        return list(self._keys)

    @property
    def size(self) -> int:
        return len(self._keys)

    def next_key(self) -> str:
        """Key kế tiếp còn sống; nếu tất cả đang cooldown thì lấy cái hết hạn sớm nhất."""
        now = time.time()
        with self._lock:
            n = len(self._keys)
            for _ in range(n):
                k = self._keys[self._idx % n]
                self._idx += 1
                if now >= self._cooldown_until.get(k, 0.0):
                    return k
            # Tất cả đang nghỉ — chọn key hồi sớm nhất rồi dùng luôn
            best = min(self._keys, key=lambda k: self._cooldown_until.get(k, 0.0))
            self._cooldown_until.pop(best, None)
            return best

    def cooldown(self, key: str, seconds: float = 45.0) -> None:
        k = (key or "").strip()
        if not k:
            return
        with self._lock:
            self._cooldown_until[k] = time.time() + max(1.0, seconds)
