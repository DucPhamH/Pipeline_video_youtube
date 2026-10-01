"""VieNeu-TTS, CPU ONNX. Gói vieneu cài riêng; CI không tải model."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from io import BytesIO
from pathlib import Path

from platform_.config import config
from platform_.db import SessionLocal
from tts.infrastructure.persistence.models import ClonedVoiceModel

_lock = threading.Lock()
_models: dict[str, object] = {}
_GPU_MISSING = "Máy đang chạy phần đọc không thấy GPU CUDA. Cần cài vieneu[cuda]."


class VieNeuNotInstalled(RuntimeError):
    pass


def available() -> bool:
    try:
        import vieneu  # noqa: F401
    except ImportError:
        return False
    return True


def gpu_ready() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def _materialize_snapshots(cache: Path) -> None:
    """HF cache để file ONNX thành symlink sang blob khác thư mục. ORT từ chối.
    Đổi symlink trong snapshot thành hardlink cùng thư mục với file .data."""
    hub = cache / "hub"
    if not hub.is_dir():
        return
    for path in hub.glob("models--*/snapshots/*/**/*"):
        if not path.is_symlink():
            continue
        target = path.resolve()
        if not target.is_file():
            continue
        path.unlink()
        try:
            os.link(target, path)
        except OSError:
            shutil.copyfile(target, path)


def _load(backend: str):
    if not available():
        raise VieNeuNotInstalled("Chưa cài vieneu")
    if backend == "pytorch" and not gpu_ready():
        raise RuntimeError(_GPU_MISSING)
    cache = config.resolved_vieneu_dir()
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "hub"))
    from vieneu import Vieneu

    kwargs = {"backend": "pytorch", "device": "cuda"} if backend == "pytorch" else {"backend": "onnx"}
    try:
        return Vieneu(**kwargs)
    except Exception as exc:
        if backend == "onnx" and "External data path" in str(exc):
            _materialize_snapshots(cache)
            return Vieneu(**kwargs)
        raise


def _get(device: str = "cpu"):
    backend = "pytorch" if device == "gpu" else "onnx"
    with _lock:
        model = _models.get(backend)
        if model is None:
            model = _load(backend)
            _models[backend] = model
        return model


def gender_from_label(label: str) -> str:
    low = (label or "").lower()
    if "nữ" in low or "female" in low:
        return "Female"
    if "male" in low or re.search(r"(^|[\s(])nam([\s)]|$)", low):
        return "Male"
    return "Unknown"


def list_presets() -> list[tuple[str, str, str]]:
    """(id, label, gender). Id là tên SDK dùng cho infer(voice=)."""
    model = _get()
    with _lock:
        rows = list(model.list_preset_voices())
    out: list[tuple[str, str, str]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        label, voice_id = str(row[0]), str(row[1])
        voice = voice_id or label
        out.append((voice, label or voice, gender_from_label(label)))
    return out


def clone_path(voice: str) -> Path:
    if not re.fullmatch(r"clone:\d+", voice or ""):
        raise RuntimeError("Giọng clone không hợp lệ")
    vid = int(voice.split(":", 1)[1])
    db = SessionLocal()
    try:
        row = db.get(ClonedVoiceModel, vid)
        rel = row.audio_path if row is not None else ""
    finally:
        db.close()
    if not rel:
        raise RuntimeError("Không có giọng đã ghi")
    root = config.resolved_audio_dir().resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise RuntimeError("File giọng không còn")
    return path


def _wav_bytes(model, audio) -> bytes:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    name = handle.name
    handle.close()
    try:
        model.save(audio, name)
        return Path(name).read_bytes()
    finally:
        Path(name).unlink(missing_ok=True)


def _concat_wav(parts: list[bytes]) -> bytes:
    frames = b""
    params = None
    for blob in parts:
        with wave.open(BytesIO(blob), "rb") as src:
            current = (src.getnchannels(), src.getsampwidth(), src.getframerate())
            if params is None:
                params = current
            elif current != params:
                raise RuntimeError("Các đoạn VieNeu không cùng định dạng")
            frames += src.readframes(src.getnframes())
    if params is None:
        raise RuntimeError("Engine không trả audio")
    out = BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setnchannels(params[0])
        dst.setsampwidth(params[1])
        dst.setframerate(params[2])
        dst.writeframes(frames)
    return out.getvalue()


def _ffmpeg_mp3(wav: bytes) -> bytes | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
        input=wav,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def synthesize(pieces: list[tuple[str, str]], device: str = "cpu") -> tuple[bytes, str]:
    """Trả (bytes, 'mp3'|'wav'). Có ffmpeg thì mp3. device cpu = ONNX, gpu = PyTorch."""
    model = _get(device)
    wavs: list[bytes] = []
    with _lock:
        for voice, text in pieces:
            if voice.startswith("clone:"):
                audio = model.infer(text, ref_audio=str(clone_path(voice)), denoise=True)
            else:
                audio = model.infer(text, voice=voice)
            wavs.append(_wav_bytes(model, audio))
    merged = _concat_wav(wavs)
    mp3 = _ffmpeg_mp3(merged)
    if mp3 is not None:
        return mp3, "mp3"
    return merged, "wav"
