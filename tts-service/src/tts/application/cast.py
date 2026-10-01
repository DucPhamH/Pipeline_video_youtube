"""Nhận diện nhân vật một lần, rồi gắn câu từng chương lúc đọc."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter

from sqlalchemy.orm import Session

from tts.application.pieces import chunk_text, split_roles
from tts.infrastructure.persistence.models import CastMemberModel, WorkModel
from tts.infrastructure.ai_chat import complete

log = logging.getLogger(__name__)

_SAMPLE_CHARS = 6000
_MIN_COVERAGE = 0.95
# Thoại tách bằng regex (không biết ai nói) — đọc bằng giọng thoại nếu có.
UNKNOWN_DIALOGUE = "dialogue"
_TAG_CHARS = 4000
_GENDERS = {"male", "female", "unknown"}
_NARRATOR = {"narrator", "người kể", "nguoi ke", "旁白"}

_DETECT_SYSTEM = (
    "Liệt kê nhân vật có lời thoại hoặc được nhắc tên trong đoạn truyện. "
    "Chỉ trả một JSON array, không markdown. "
    'Mỗi phần tử: {"name":"tên","gender":"male"|"female"|"unknown"}. '
    "Bỏ người kể. Tối đa 30 tên. gender là unknown nếu không chắc. Không bịa tên."
)

_TAG_SYSTEM = (
    "Chia chương thành các đoạn theo người nói. Chỉ trả một JSON array, không markdown. "
    'Mỗi phần tử: {"speaker":"narrator hoặc đúng tên nhân vật","text":"nguyên văn"}. '
    "Giữ nguyên chữ, không dịch, không tóm tắt, không thêm lời. "
    "Lời kể là narrator. Câu thoại gán đúng tên nếu chắc, không chắc thì narrator."
)


def parse_json_array(raw: str) -> list:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Model không trả JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("Model không trả JSON")
    return data


def sample_text(work: WorkModel) -> str:
    parts: list[str] = []
    total = 0
    for chapter in sorted(work.chapters, key=lambda row: row.index)[:2]:
        piece = (chapter.text or "").strip()
        room = _SAMPLE_CHARS - total
        if room <= 0:
            break
        parts.append(piece[:room])
        total += min(len(piece), room)
    text = "\n\n".join(part for part in parts if part).strip()
    if not text:
        raise ValueError("Không có chữ để nhận diện")
    return text


def detect_cast(db: Session, work: WorkModel, provider_id: int) -> None:
    raw = complete(
        provider_id,
        [
            {"role": "system", "content": _DETECT_SYSTEM},
            {"role": "user", "content": sample_text(work)},
        ],
    )
    rows = parse_json_array(raw)
    db.query(CastMemberModel).filter(CastMemberModel.work_id == work.id).delete()
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:120]
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        gender = str(item.get("gender") or "unknown").strip().lower()
        if gender not in _GENDERS:
            gender = "unknown"
        db.add(CastMemberModel(work_id=work.id, name=name, gender=gender, voice=""))
        if len(seen) >= 30:
            break
    db.commit()


def replace_cast(db: Session, work: WorkModel, members: list[dict]) -> None:
    db.query(CastMemberModel).filter(CastMemberModel.work_id == work.id).delete()
    seen: set[str] = set()
    for item in members:
        name = str(item.get("name") or "").strip()[:120]
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        gender = str(item.get("gender") or "unknown").strip().lower()
        if gender not in _GENDERS:
            raise ValueError("gender phải là male, female hoặc unknown")
        voice = str(item.get("voice") or "").strip()[:80]
        if "\n" in voice or "\x00" in voice:
            raise ValueError("Giọng không hợp lệ")
        db.add(CastMemberModel(work_id=work.id, name=name, gender=gender, voice=voice))
        if len(seen) >= 40:
            break
    db.commit()


def _tag_chunks(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= _TAG_CHARS:
        return [raw]
    out: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n", raw):
        para = para.strip()
        if not para:
            continue
        if len(para) > _TAG_CHARS:
            if buf:
                out.append(buf)
                buf = ""
            for start in range(0, len(para), _TAG_CHARS):
                out.append(para[start : start + _TAG_CHARS])
            continue
        if buf and len(buf) + 2 + len(para) > _TAG_CHARS:
            out.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}".strip() if buf else para
    if buf:
        out.append(buf)
    return out or [raw[:_TAG_CHARS]]


def _canon_speaker(speaker: str, names: dict[str, str]) -> str:
    key = (speaker or "").strip().casefold()
    if key in _NARRATOR:
        return "narrator"
    return names.get(key, "narrator")


def tag_chapter(text: str, cast: list[dict], provider_id: int) -> list[dict]:
    names = {str(row["name"]).casefold(): str(row["name"]) for row in cast if row.get("name")}
    known = ", ".join(names.values()) or "(không có)"
    system = f"{_TAG_SYSTEM} Nhân vật đã biết: {known}."
    pieces: list[dict] = []
    for chunk in _tag_chunks(text):
        raw = complete(
            provider_id,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": chunk},
            ],
        )
        tagged: list[dict] = []
        try:
            items = parse_json_array(raw)
        except ValueError:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            body = str(item.get("text") or "").strip()
            if not body:
                continue
            speaker = _canon_speaker(str(item.get("speaker") or ""), names)
            tagged.append({"speaker": speaker, "text": body})
        ratio = coverage(chunk, "".join(p["text"] for p in tagged))
        if ratio < _MIN_COVERAGE:
            log.warning("tag_chapter: AI trả thiếu/thừa chữ (%.0f%%), tách bằng regex", ratio * 100)
            tagged = _regex_pieces(chunk)
        pieces.extend(tagged)
    if not pieces:
        raise ValueError("Không tách được câu")
    return pieces


def _letters(text: str) -> Counter:
    # NFC trước và sau casefold: "ế" NFD là e + dấu (dấu không isalnum) → đếm lệch so với bản NFC.
    folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text or "").casefold())
    return Counter(ch for ch in folded if ch.isalnum())


def coverage(source: str, joined: str) -> float:
    """Tỉ lệ chữ khớp giữa bản gốc và các đoạn AI trả (bỏ dấu câu, khoảng trắng); thiếu hay thừa đều bị trừ."""
    src = _letters(source)
    out = _letters(joined)
    total_src = sum(src.values())
    total_out = sum(out.values())
    if total_src == 0:
        return 1.0 if total_out == 0 else 0.0
    if total_out == 0:
        return 0.0
    shared = sum((src & out).values())
    return min(shared / total_src, shared / total_out)


def _regex_pieces(chunk: str) -> list[dict]:
    return [
        {"speaker": "narrator" if role == "narrator" else UNKNOWN_DIALOGUE, "text": body}
        for role, body in split_roles(chunk, dialogue=True)
    ]


def voices_for_pieces(pieces: list[dict], cast: list[dict], params) -> list[tuple[str, str]]:
    by_name = {str(row["name"]).casefold(): row for row in cast if row.get("name")}
    out: list[tuple[str, str]] = []
    for piece in pieces:
        speaker = str(piece.get("speaker") or "narrator")
        body = str(piece.get("text") or "").strip()
        if not body:
            continue
        if speaker == "narrator":
            voice = params.voice
        elif speaker == UNKNOWN_DIALOGUE and speaker.casefold() not in by_name:
            voice = params.dialogue_voice or params.voice
        else:
            voice = _member_voice(by_name.get(speaker.casefold()), params)
        for chunk in chunk_text(body):
            out.append((voice, chunk))
    return out


def _member_voice(member: dict | None, params) -> str:
    if member is None:
        return params.voice
    own = str(member.get("voice") or "").strip()
    if own:
        return own
    gender = str(member.get("gender") or "")
    if gender == "male" and params.male_voice:
        return params.male_voice
    if gender == "female" and params.female_voice:
        return params.female_voice
    return params.voice
