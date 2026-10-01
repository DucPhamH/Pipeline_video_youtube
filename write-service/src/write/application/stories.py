"""Truyện người dùng tự dựng: dàn ý, viết từng chương, viết tiếp đến hết."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from platform_.db import SessionLocal
from write.infrastructure.persistence.models import (
    StoryChapterModel,
    StoryCharacterModel,
    StoryModel,
)
from write.infrastructure.ai_chat import complete, iter_content

_MIN_CHAPTERS = 4
_MAX_CHAPTERS = 40
_MAX_CHARACTERS = 8
_TAIL_CHARS = 1200
_lock = threading.Lock()
_running: set[int] = set()


class StoryNotFound(Exception):
    pass


class StoryConflict(Exception):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _clean_characters(rows: list[dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        out.append((name[:80], str(row.get("role") or "").strip()[:200]))
        if len(out) >= _MAX_CHARACTERS:
            break
    return out


def _replace_characters(story: StoryModel, rows: list[dict]) -> None:
    story.characters.clear()
    for position, (name, role) in enumerate(_clean_characters(rows)):
        story.characters.append(StoryCharacterModel(position=position, name=name, role=role))


def _blank_chapter(index: int) -> StoryChapterModel:
    return StoryChapterModel(index=index, title=f"Chương {index}", beat="", text="")


def _require(db: Session, story_id: int) -> StoryModel:
    story = db.get(StoryModel, story_id)
    if story is None:
        raise StoryNotFound()
    return story


def _touch(story: StoryModel) -> None:
    story.updated_at = _now()


def create_story(
    db: Session,
    *,
    title: str,
    premise: str,
    ending: str,
    chapter_count: int,
    provider_id: int,
    characters: list[dict],
) -> StoryModel:
    title = title.strip()
    premise = premise.strip()
    if not title or not premise:
        raise ValueError("Cần tên truyện và gợi ý")
    if chapter_count < _MIN_CHAPTERS or chapter_count > _MAX_CHAPTERS:
        raise ValueError("Số chương từ 4 đến 40")
    story = StoryModel(
        title=title[:255],
        premise=premise[:4000],
        ending=(ending.strip() or "để ngỏ")[:500],
        chapter_count=chapter_count,
        provider_id=provider_id,
        status="idle",
    )
    _replace_characters(story, characters)
    story.chapters = [_blank_chapter(i) for i in range(1, chapter_count + 1)]
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def list_stories(db: Session) -> list[StoryModel]:
    return db.query(StoryModel).order_by(StoryModel.updated_at.desc(), StoryModel.id.desc()).all()


def get_story(db: Session, story_id: int) -> StoryModel:
    return _require(db, story_id)


def update_story(
    db: Session,
    story_id: int,
    *,
    title: str | None = None,
    premise: str | None = None,
    ending: str | None = None,
    chapter_count: int | None = None,
    provider_id: int | None = None,
    characters: list[dict] | None = None,
) -> StoryModel:
    story = _require(db, story_id)
    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("Cần tên truyện")
        story.title = cleaned[:255]
    if premise is not None:
        cleaned = premise.strip()
        if not cleaned:
            raise ValueError("Cần gợi ý")
        story.premise = cleaned[:4000]
    if ending is not None:
        story.ending = (ending.strip() or "để ngỏ")[:500]
    if provider_id is not None:
        story.provider_id = provider_id
    if characters is not None:
        _replace_characters(story, characters)
    if chapter_count is not None and chapter_count != story.chapter_count:
        if chapter_count < _MIN_CHAPTERS or chapter_count > _MAX_CHAPTERS:
            raise ValueError("Số chương từ 4 đến 40")
        if chapter_count < story.chapter_count:
            blocked = [c.index for c in story.chapters if c.index > chapter_count and (c.text or "").strip()]
            if blocked:
                raise ValueError("Chương đã có chữ, không thu số chương")
            story.chapters = [c for c in story.chapters if c.index <= chapter_count]
        else:
            have = {c.index for c in story.chapters}
            for index in range(1, chapter_count + 1):
                if index not in have:
                    story.chapters.append(_blank_chapter(index))
        story.chapter_count = chapter_count
    _touch(story)
    db.commit()
    db.refresh(story)
    return story


def delete_story(db: Session, story_id: int) -> None:
    story = _require(db, story_id)
    if story.status in ("writing", "stopping"):
        raise StoryConflict("Đang viết, dừng trước khi xóa")
    db.delete(story)
    db.commit()


def update_chapter(
    db: Session,
    story_id: int,
    index: int,
    *,
    title: str | None = None,
    beat: str | None = None,
    text: str | None = None,
) -> StoryModel:
    story = _require(db, story_id)
    chapter = _chapter(story, index)
    if title is not None:
        chapter.title = title.strip()[:255] or f"Chương {index}"
    if beat is not None:
        chapter.beat = beat.strip()[:500]
    if text is not None:
        chapter.text = text
    _touch(story)
    db.commit()
    db.refresh(story)
    return story


def _chapter(story: StoryModel, index: int) -> StoryChapterModel:
    chapter = next((c for c in story.chapters if c.index == index), None)
    if chapter is None:
        raise StoryNotFound()
    return chapter


def _brief(story: StoryModel) -> str:
    people = "\n".join(f"- {c.name}: {c.role}".rstrip(": ") for c in story.characters) or "(không có)"
    outline = "\n".join(f"{c.index}. {c.title} — {c.beat}" for c in story.chapters)
    return (
        f"GỢI Ý:\n{story.premise}\n\nKẾT:\n{story.ending}\n\n"
        f"SỐ CHƯƠNG: {story.chapter_count}\n\nNHÂN VẬT:\n{people}\n\nDÀN Ý:\n{outline}"
    )


def ask(db: Session, provider_id: int, *, system: str, user: str) -> str:
    del db
    return complete(
        provider_id,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
    )


def _parse_outline(raw: str, count: int) -> list[tuple[str, str]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("AI không trả dàn ý đúng dạng. AI Mock không lập được dàn ý, chọn AI thật")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list) or len(data) != count:
        raise ValueError("AI không trả đúng số chương")
    rows: list[tuple[str, str]] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError("AI không trả dàn ý đúng dạng")
        title = str(item.get("title") or f"Chương {i}").strip()[:255]
        beat = str(item.get("beat") or "").strip()[:500]
        rows.append((title or f"Chương {i}", beat))
    return rows


def generate_outline(db: Session, story_id: int, *, replace: bool) -> StoryModel:
    story = _require(db, story_id)
    if story.status in ("writing", "stopping"):
        raise StoryConflict("Đang viết")
    if any((c.beat or "").strip() for c in story.chapters) and not replace:
        raise StoryConflict("Dàn ý đã có. Gửi replace để viết lại")
    if story.provider_id is None:
        raise ValueError("Chọn AI")
    raw = ask(
        db,
        story.provider_id,
        system=(
            "OUTLINE. Bạn lập dàn ý tiểu thuyết mạng tiếng Việt. "
            "Chỉ trả về JSON array đúng số chương, mỗi phần tử có title và beat. "
            "beat là một câu. Chương cuối đi về câu kết. Không markdown."
        ),
        user=_brief(story),
    )
    rows = _parse_outline(raw, story.chapter_count)
    for chapter, (title, beat) in zip(story.chapters, rows, strict=True):
        chapter.title = title
        chapter.beat = beat
    story.write_error = ""
    _touch(story)
    db.commit()
    db.refresh(story)
    return story


def _previous_tail(story: StoryModel, index: int) -> str:
    prev = next((c for c in story.chapters if c.index == index - 1), None)
    if prev is None or not (prev.text or "").strip():
        return ""
    return prev.text.strip()[-_TAIL_CHARS:]


def _chapter_messages(story: StoryModel, chapter: StoryChapterModel) -> list[dict[str, str]]:
    tail = _previous_tail(story, chapter.index)
    last = "Đây là chương cuối." if chapter.index == story.chapter_count else "Chưa phải chương cuối."
    return [
        {
            "role": "system",
            "content": (
                "CHAPTER. Bạn viết một chương tiểu thuyết mạng tiếng Việt. "
                "Chỉ trả lời bằng văn chương, không tiêu đề, không markdown. "
                "Giữ đúng beat của chương này. Câu kết của cả truyện chỉ hiện rõ ở chương cuối."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{_brief(story)}\n\nCHƯƠNG {chapter.index} / {story.chapter_count}\n"
                f"BEAT: {chapter.beat}\n{last}\n\nĐOẠN CUỐI CHƯƠNG TRƯỚC:\n{tail or '(không có)'}"
            ),
        },
    ]


def _clean_chapter(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return text[:30000]


def compose_chapter(db: Session, story: StoryModel, chapter: StoryChapterModel) -> str:
    if story.provider_id is None:
        raise ValueError("Chọn AI")
    messages = _chapter_messages(story, chapter)
    raw = ask(db, story.provider_id, system=messages[0]["content"], user=messages[1]["content"])
    text = _clean_chapter(raw)
    if not text:
        raise ValueError("AI trả chương rỗng")
    return text


def write_chapter(db: Session, story_id: int, index: int, *, force: bool) -> StoryModel:
    story = _require(db, story_id)
    if story.status in ("writing", "stopping"):
        raise StoryConflict("Đang viết cả truyện")
    chapter = _chapter(story, index)
    if (chapter.text or "").strip() and not force:
        raise StoryConflict("Chương đã có chữ")
    chapter.text = compose_chapter(db, story, chapter)
    story.write_error = ""
    _touch(story)
    db.commit()
    db.refresh(story)
    return story


def prepare_stream(db: Session, story_id: int, index: int, *, force: bool) -> tuple[StoryModel, StoryChapterModel]:
    story = _require(db, story_id)
    if story.status in ("writing", "stopping"):
        raise StoryConflict("Đang viết cả truyện")
    chapter = _chapter(story, index)
    if (chapter.text or "").strip() and not force:
        raise StoryConflict("Chương đã có chữ")
    if story.provider_id is None:
        raise ValueError("Chọn AI")
    return story, chapter


def open_chapter_stream(db: Session, story_id: int, index: int, *, force: bool):
    """Kiểm tra rồi trả dữ liệu thuần để stream sau khi session của request đóng."""
    story, chapter = prepare_stream(db, story_id, index, force=force)
    if story.provider_id is None:
        raise ValueError("Chọn AI")
    return story.provider_id, _chapter_messages(story, chapter), story.id, chapter.index


def iter_saved_chapter(provider_id: int, messages: list[dict[str, str]], story_id: int, index: int):
    parts: list[str] = []
    for delta in iter_content(provider_id, messages):
        parts.append(delta)
        yield delta
    text = _clean_chapter("".join(parts))
    if not text:
        raise ValueError("AI trả chương rỗng")
    save_streamed_chapter(story_id, index, text)


def save_streamed_chapter(story_id: int, index: int, text: str) -> None:
    db = SessionLocal()
    try:
        story = _require(db, story_id)
        chapter = _chapter(story, index)
        chapter.text = text
        story.write_error = ""
        _touch(story)
        db.commit()
    finally:
        db.close()


def run_write_all(story_id: int) -> None:
    db = SessionLocal()
    try:
        while True:
            db.expire_all()
            story = db.get(StoryModel, story_id)
            if story is None:
                return
            if story.status != "writing":
                if story.status == "stopping":
                    story.status = "idle"
                    _touch(story)
                    db.commit()
                return
            chapter = next((c for c in story.chapters if not (c.text or "").strip()), None)
            if chapter is None:
                story.status = "idle"
                _touch(story)
                db.commit()
                return
            chapter_index = chapter.index
            try:
                produced = compose_chapter(db, story, chapter)
            except Exception as exc:  # noqa: BLE001 — giữ chương đã xong, báo lỗi cho lần sau
                db.expire_all()
                story = db.get(StoryModel, story_id)
                if story is None:
                    return
                story.status = "idle"
                story.write_error = str(exc)[:500]
                _touch(story)
                db.commit()
                return
            db.expire_all()
            story = db.get(StoryModel, story_id)
            if story is None:
                return
            chapter = next(c for c in story.chapters if c.index == chapter_index)
            chapter.text = produced
            story.write_error = ""
            if story.status != "writing":
                story.status = "idle"
            _touch(story)
            db.commit()
            if story.status == "idle":
                return
    finally:
        db.close()
        with _lock:
            _running.discard(story_id)


def start_write_all(db: Session, story_id: int) -> StoryModel:
    story = _require(db, story_id)
    if story.status == "writing":
        raise StoryConflict("Đang viết")
    if not any(not (c.text or "").strip() for c in story.chapters):
        raise ValueError("Không còn chương trống")
    story.status = "writing"
    story.write_error = ""
    _touch(story)
    db.commit()
    with _lock:
        if story_id not in _running:
            _running.add(story_id)
            threading.Thread(target=run_write_all, args=(story_id,), daemon=True).start()
    db.refresh(story)
    return story


def stop_write(db: Session, story_id: int) -> StoryModel:
    story = _require(db, story_id)
    if story.status not in ("writing", "stopping"):
        return story
    with _lock:
        alive = story_id in _running
    story.status = "stopping" if alive else "idle"
    _touch(story)
    db.commit()
    db.refresh(story)
    return story


INTERRUPTED = "Bị dừng do khởi động lại. Bấm viết tiếp để chạy nốt."


def recover_interrupted(db: Session) -> int:
    """Thread viết sống trong process. Restart thì truyện đang viết phải về idle."""
    stuck = db.query(StoryModel).filter(StoryModel.status.in_(("writing", "stopping"))).all()
    for story in stuck:
        story.status = "idle"
        story.write_error = INTERRUPTED
        _touch(story)
    if stuck:
        db.commit()
    return len(stuck)
