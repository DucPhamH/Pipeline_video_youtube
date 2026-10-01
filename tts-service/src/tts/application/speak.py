"""Ghép đoạn đọc và cache file mp3 theo chữ + giọng + thông số."""
from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from platform_.config import config
from tts.application.pieces import pieces_for
from tts.infrastructure.engines.edge import EdgeEngine
from tts.infrastructure.engines.mock import MockEngine
from tts.infrastructure.engines.vieneu import synthesize

# Khoá theo cache key: cùng chữ + giọng thì đợi nhau, khác key (vd. nghe thử) chạy song song.
_guard = threading.Lock()
_key_locks: dict[str, list] = {}


@contextmanager
def _key_lock(key: str):
    with _guard:
        entry = _key_locks.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _guard:
            entry[1] -= 1
            if entry[1] <= 0:
                _key_locks.pop(key, None)


@dataclass(frozen=True)
class SpeakParams:
    engine: str
    voice: str
    dialogue_voice: str
    rate: str
    pitch: str
    volume: str
    style: str
    male_voice: str = ""
    female_voice: str = ""
    device: str = "cpu"


def cache_key(text: str, params: SpeakParams, voiced: list[tuple[str, str]] | None = None) -> str:
    parts = [
        text or "",
        params.engine,
        params.voice,
        params.dialogue_voice,
        params.rate,
        params.pitch,
        params.volume,
        params.style,
        params.device if params.engine == "vieneu" else "",
    ]
    if voiced is not None:
        parts.append(params.male_voice)
        parts.append(params.female_voice)
        parts.append("\n".join(f"{voice}\0{chunk}" for voice, chunk in voiced))
    blob = "\0".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_engine(name: str):
    if name == "mock":
        return MockEngine()
    if name == "edge":
        return EdgeEngine()
    raise ValueError(f"engine không hợp lệ: {name}")


def _cache_file(key: str, suffix: str) -> Path:
    path = config.resolved_audio_dir() / "cache" / f"{key}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _find_cache(key: str) -> Path | None:
    for suffix in ("mp3", "wav"):
        path = _cache_file(key, suffix)
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _speak_bytes(spoken: list[tuple[str, str]], params: SpeakParams) -> tuple[bytes, str]:
    if params.engine == "vieneu":
        return synthesize(spoken, device=params.device)
    engine = get_engine(params.engine)
    audio = bytearray()
    for voice, chunk in spoken:
        audio.extend(
            engine.speak(
                text=chunk,
                voice=voice,
                rate=params.rate,
                pitch=params.pitch,
                volume=params.volume,
                style=params.style,
            )
        )
    if not audio:
        raise RuntimeError("Engine không trả audio")
    return bytes(audio), "mp3"


def render(
    text: str,
    params: SpeakParams,
    voiced: list[tuple[str, str]] | None = None,
) -> tuple[Path, str, bool]:
    """Trả (file, cache_key, từ cache). voiced là (giọng, chữ) khi đọc theo nhân vật."""
    if voiced is None:
        pieces = pieces_for(text, params.dialogue_voice)
        spoken = [
            (params.dialogue_voice if role == "dialogue" and params.dialogue_voice else params.voice, chunk)
            for role, chunk in pieces
        ]
        key = cache_key(text, params)
    else:
        spoken = [(voice, chunk) for voice, chunk in voiced if chunk.strip()]
        key = cache_key(text, params, spoken)
    if not spoken:
        raise ValueError("Chương rỗng")
    with _key_lock(key):
        cached = _find_cache(key)
        if cached is not None:
            return cached, key, True
        audio, suffix = _speak_bytes(spoken, params)
        path = _cache_file(key, suffix)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(audio)
        tmp.replace(path)
        return path, key, False


def relative_audio(path: Path) -> str:
    root = config.resolved_audio_dir().resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError("File audio nằm ngoài thư mục cache")
    return str(resolved.relative_to(root))


def absolute_audio(rel: str) -> Path:
    root = config.resolved_audio_dir().resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Đường dẫn audio không hợp lệ")
    return path
