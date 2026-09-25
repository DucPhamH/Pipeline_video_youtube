"""Fingerprint nội dung chương — ổn định cho cache / sync."""
from __future__ import annotations

import hashlib
import re


def content_fingerprint(*texts: str, max_chars: int = 4000) -> str:
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


def glossary_hash(terms: list[tuple[str, str, bool]]) -> str:
    """terms: (source, target, protected) — sorted for ổn định."""
    parts = [
        f"{s}\t{t}\t{1 if p else 0}"
        for s, t, p in sorted(terms, key=lambda x: x[0].casefold())
    ]
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def cache_key(
    *,
    source_text: str,
    mode: str,
    lang_src: str,
    lang_tgt: str,
    model: str,
    prompt_version: str,
    glossary_hash_value: str = "",
    mode_params_hash_value: str = "",
) -> str:
    blob = "\0".join(
        [
            source_text or "",
            mode,
            lang_src,
            lang_tgt,
            model,
            prompt_version,
            glossary_hash_value or "",
            mode_params_hash_value or "",
        ]
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
