"""Giải mã nội dung chương ciweimao (AES-CBC) — port logic công khai từ
novel-downloader `my_encryt_extend` (đọc chapter account đã có quyền)."""
from __future__ import annotations

import base64


def ciweimao_decrypt(content: str, keys: list[str], access_key: str) -> str:
    if not keys:
        raise ValueError("keys must not be empty")
    if not access_key:
        raise ValueError("access_key must not be empty")

    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError as exc:
        raise ImportError(
            "Thiếu pycryptodome — pip install pycryptodome (ciweimao AES)"
        ) from exc

    o = list(access_key)
    t = len(keys)
    selected_keys = [keys[ord(o[-1]) % t], keys[ord(o[0]) % t]]

    for k in selected_keys:
        raw = base64.b64decode(content)
        key = base64.b64decode(k)
        iv = raw[:16]
        text = raw[16:]
        decoded = AES.new(key, AES.MODE_CBC, iv).decrypt(text)
        decoded = unpad(decoded, AES.block_size)
        content = decoded.decode("utf-8")
    return content
