"""Challenge cookie dùng chung — pattern 17k `arg1` → `acw_sc__v2`.

Site khác có challenge tương tự có thể tái dùng `_reorder` / `_xor_hex`
hoặc thêm solver riêng cạnh đây.
"""
from __future__ import annotations

import base64
import random
import re

_RE_ARG1 = re.compile(r"var\s+arg1\s*=\s*(['\"])\s*([0-9A-F]+)\s*\1", re.I)
_ORDER_IDX = [
    14, 34, 28, 23, 32, 15, 0, 37, 9, 8, 18, 30, 39, 26, 21, 22, 24, 12, 5, 10,
    38, 17, 19, 7, 13, 20, 31, 25, 1, 29, 6, 3, 16, 4, 2, 27, 33, 36, 11, 35,
]
_SEC = base64.b64decode(b"MAAXYACFYAYGFQFTMANpACeAA3U=")


def create_guid() -> str:
    template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return "".join(
        format(random.randint(0, 15), "x")
        if ch == "x"
        else format((random.randint(0, 15) & 0x3) | 0x8, "x")
        if ch == "y"
        else ch
        for ch in template
    )


def solve_acw_sc_v2(html: str) -> str | None:
    """Trả cookie value `acw_sc__v2` hoặc None nếu trang không có challenge."""
    match = _RE_ARG1.search(html)
    if not match:
        return None
    arg1 = match.group(2).strip()
    reordered = "".join(arg1[i] for i in _ORDER_IDX)
    return bytes(
        x ^ y for x, y in zip(bytes.fromhex(reordered), _SEC, strict=False)
    ).hex()


def merge_challenge_cookies(
    base: dict[str, str] | None,
    html: str,
    *,
    ensure_guid: bool = True,
) -> dict[str, str]:
    """Cập nhật dict cookie sau khi đọc HTML challenge (17k-style)."""
    out = dict(base or {})
    if ensure_guid and "GUID" not in out:
        out["GUID"] = create_guid()
    solved = solve_acw_sc_v2(html)
    if solved:
        out["acw_sc__v2"] = solved
    return out
