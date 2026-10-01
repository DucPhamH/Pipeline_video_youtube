"""Tạo Work từ TXT, EPUB, hoặc chương đã dịch."""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from platform_.config import config
from tts.application.voices import default_voice, lang_primary, presets_for
from tts.infrastructure.parsers.epub import parse_epub
from tts.infrastructure.parsers.txt import ParsedChapter, split_txt_chapters
from tts.infrastructure.persistence.models import (
    CastMemberModel,
    ChapterModel,
    JobModel,
    ReadingModel,
    SegmentModel,
    WorkModel,
)

_RATE = re.compile(r"^[+-]\d+%$")
_PITCH = re.compile(r"^[+-]\d+Hz$")
_EDGE_VOICE = re.compile(
    r"^(?:[a-z]{2,}-[A-Za-z0-9:-]+Neural|Microsoft Server Speech Text to Speech Voice \(.+,.+\))$"
)
_STYLE = re.compile(r"^[A-Za-z0-9-]{0,40}$")
_ENGINES = {"mock", "edge", "vieneu"}


def _ok_voice(engine: str, voice: str) -> bool:
    if engine == "vieneu":
        if re.fullmatch(r"clone:\d+", voice):
            return True
        return 1 <= len(voice) <= 80 and "\n" not in voice and "\x00" not in voice
    return bool(_EDGE_VOICE.match(voice))


def _cover_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ".img"


def _store_cover(work_id: int, data: bytes) -> str:
    if not data:
        return ""
    rel = f"covers/{work_id}{_cover_ext(data)}"
    path = config.resolved_audio_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def _nfc(text: str) -> str:
    """Tiếng Việt từ EPUB / bản dịch có thể ở dạng NFD (dấu tách rời) — gom về NFC một lần lúc nhập."""
    return unicodedata.normalize("NFC", text or "")


def _usable(chapters: list[ParsedChapter]) -> list[ParsedChapter]:
    usable = [c for c in chapters if (c.text or "").strip()]
    if not usable:
        raise ValueError("Không có chương")
    seen: set[int] = set()
    for ch in usable:
        if ch.index in seen:
            raise ValueError(f"Trùng chương {ch.index}")
        seen.add(ch.index)
    return usable


def _add_chapters(db: Session, work: WorkModel, chapters: list[ParsedChapter]) -> None:
    for ch in _usable(chapters):
        db.add(
            ChapterModel(
                work_id=work.id,
                index=ch.index,
                title=_nfc(ch.title or f"Chapter {ch.index}")[:255],
                text=_nfc(ch.text),
            )
        )


def _replace_chapters(db: Session, work: WorkModel, chapters: list[ParsedChapter]) -> None:
    """Ghi đè chương theo index. Lần đọc đang chạy giữ bản chữ đã chụp lúc bắt đầu."""
    usable = _usable(chapters)
    by_index = {c.index: c for c in work.chapters}
    seen = {ch.index for ch in usable}
    for ch in usable:
        title = _nfc(ch.title or f"Chapter {ch.index}")[:255]
        text = _nfc(ch.text)
        row = by_index.get(ch.index)
        if row is None:
            db.add(ChapterModel(work_id=work.id, index=ch.index, title=title, text=text))
        else:
            row.title = title
            row.text = text
    for index, row in by_index.items():
        if index not in seen:
            db.delete(row)


def create_work(
    db: Session,
    *,
    title: str,
    author: str,
    lang: str,
    source_type: str,
    chapters: list[ParsedChapter],
    external_id: str | None = None,
    cover: bytes = b"",
) -> WorkModel:
    work = WorkModel(
        title=_nfc(title or "untitled")[:255],
        author=_nfc(author or "")[:255],
        lang=(lang or "vi")[:20],
        source_type=source_type,
        external_id=(external_id or None),
    )
    db.add(work)
    db.flush()
    _add_chapters(db, work, chapters)
    if cover:
        work.cover_path = _store_cover(work.id, cover)
    db.commit()
    db.refresh(work)
    return work


def import_txt(db: Session, *, title: str, author: str, lang: str, text: str) -> WorkModel:
    return create_work(
        db,
        title=title,
        author=author,
        lang=lang,
        source_type="upload",
        chapters=split_txt_chapters(text),
    )


def import_epub(db: Session, *, data: bytes, title: str, author: str, lang: str) -> WorkModel:
    parsed_title, parsed_author, chapters, cover = parse_epub(data)
    return create_work(
        db,
        title=title or parsed_title,
        author=author or parsed_author,
        lang=lang,
        source_type="upload",
        chapters=chapters,
        cover=cover,
    )


def from_translate(
    db: Session,
    *,
    title: str,
    author: str,
    lang: str,
    external_id: str,
    chapters: list[ParsedChapter],
) -> tuple[WorkModel, bool]:
    ext = (external_id or "").strip()
    if not ext:
        raise ValueError("Thiếu external_id")
    existing = db.query(WorkModel).filter(WorkModel.external_id == ext).one_or_none()
    if existing is not None:
        existing.title = _nfc(title or existing.title)[:255]
        existing.author = _nfc(author or "")[:255]
        existing.lang = (lang or existing.lang)[:20]
        _replace_chapters(db, existing, chapters)
        db.commit()
        db.refresh(existing)
        return existing, False
    work = create_work(
        db,
        title=title,
        author=author,
        lang=lang,
        source_type="translate_handoff",
        chapters=chapters,
        external_id=ext,
    )
    return work, True


def normalize_speak(
    *,
    lang: str,
    engine: str,
    voice: str,
    dialogue_voice: str,
    rate: str,
    pitch: str,
    volume: str,
    style: str,
    preset_id: str,
    male_voice: str = "",
    female_voice: str = "",
    use_cast: bool = False,
    provider_id: int | None = None,
    device: str = "cpu",
) -> dict:
    engine = (engine or "edge").strip().lower()
    if engine not in _ENGINES:
        raise ValueError("engine phải là mock, edge hoặc vieneu")
    if engine == "vieneu" and lang_primary(lang) != "vi":
        raise ValueError("VieNeu chỉ đọc tiếng Việt")
    if preset_id and engine != "vieneu":
        preset = next((p for p in presets_for(lang) if p.id == preset_id), None)
        if preset is None:
            raise ValueError(f"Không có preset {preset_id}")
        voice = voice or preset.voice
        dialogue_voice = dialogue_voice or preset.dialogue_voice
        rate = rate or preset.rate
        pitch = pitch or preset.pitch
        volume = volume or preset.volume
        style = style or preset.style
    device = (device or "cpu").strip().lower()
    if device not in ("cpu", "gpu"):
        raise ValueError("device phải là cpu hoặc gpu")
    if engine != "vieneu":
        device = "cpu"
    if engine == "vieneu" and device == "gpu":
        from tts.infrastructure.engines.vieneu import gpu_ready

        if not gpu_ready():
            raise ValueError("Máy đang chạy phần đọc không thấy GPU CUDA. Cần cài vieneu[cuda].")
    if engine == "vieneu":
        voice = (voice or "").strip()
        rate, pitch, volume, style = "+0%", "+0Hz", "+0%", ""
    else:
        voice = (voice or default_voice(lang)).strip()
    dialogue_voice = (dialogue_voice or "").strip()
    male_voice = (male_voice or "").strip()
    female_voice = (female_voice or "").strip()
    rate = (rate or "+0%").strip()
    pitch = (pitch or "+0Hz").strip()
    volume = (volume or "+0%").strip()
    style = (style or "").strip()
    if use_cast and engine in ("edge", "mock") and lang_primary(lang) == "vi":
        male_voice = male_voice or "vi-VN-NamMinhNeural"
        female_voice = female_voice or "vi-VN-HoaiMyNeural"
    if not voice:
        raise ValueError("Chọn giọng")
    if not _ok_voice(engine, voice):
        raise ValueError("Giọng không hợp lệ")
    for label, extra in (
        ("Giọng thoại", dialogue_voice),
        ("Giọng nam", male_voice),
        ("Giọng nữ", female_voice),
    ):
        if extra and not _ok_voice(engine, extra):
            raise ValueError(f"{label} không hợp lệ")
    if use_cast and (not male_voice or not female_voice):
        raise ValueError("Cần giọng nam và giọng nữ")
    if use_cast and not provider_id:
        raise ValueError("Chọn AI để gắn câu thoại")
    if not _RATE.match(rate) or not _RATE.match(volume) or not _PITCH.match(pitch):
        raise ValueError("rate, volume dạng +0%; pitch dạng +0Hz")
    if not _STYLE.match(style):
        raise ValueError("style không hợp lệ")
    return {
        "engine": engine,
        "voice": voice,
        "dialogue_voice": dialogue_voice,
        "rate": rate,
        "pitch": pitch,
        "volume": volume,
        "style": style,
        "male_voice": male_voice,
        "female_voice": female_voice,
        "use_cast": bool(use_cast),
        "provider_id": provider_id if use_cast else None,
        "device": device,
    }


def start_reading(db: Session, work: WorkModel, params: dict) -> tuple[ReadingModel, JobModel]:
    if params.get("use_cast"):
        count = db.query(CastMemberModel).filter(CastMemberModel.work_id == work.id).count()
        if count == 0:
            raise ValueError("Chưa có nhân vật — nhận diện hoặc thêm tay trước")
    reading = ReadingModel(work_id=work.id, status="queued", **params)
    db.add(reading)
    db.flush()
    job = JobModel(reading_id=reading.id, status="queued", **params)
    db.add(job)
    db.flush()
    for ch in work.chapters:
        db.add(
            SegmentModel(
                job_id=job.id,
                chapter_index=ch.index,
                status="pending",
                source_text=ch.text,
            )
        )
    db.commit()
    db.refresh(job)
    return reading, job
