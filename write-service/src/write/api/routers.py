"""Route bàn viết. AI đã lưu nằm ở translate-service, gọi qua HTTP."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from platform_.db import get_db
from write.api.schemas import (
    StoryChapterPatchIn,
    StoryCreateIn,
    StoryListOut,
    StoryOut,
    StoryPatchIn,
    StoryWriteIn,
)
from write.application.stories import (
    StoryConflict,
    StoryNotFound,
    create_story,
    delete_story,
    generate_outline,
    get_story,
    list_stories,
    iter_saved_chapter,
    open_chapter_stream,
    start_write_all,
    stop_write,
    update_chapter,
    update_story,
    write_chapter,
)
from write.infrastructure.persistence.models import StoryModel

router = APIRouter(prefix="/api/write", tags=["write"])


def _out(story: StoryModel) -> StoryOut:
    return StoryOut(
        id=story.id,
        title=story.title,
        premise=story.premise,
        ending=story.ending,
        chapter_count=story.chapter_count,
        provider_id=story.provider_id,
        status=story.status,
        write_error=story.write_error or "",
        characters=[{"name": c.name, "role": c.role} for c in story.characters],
        chapters=[
            {"index": c.index, "title": c.title, "beat": c.beat, "text": c.text or ""}
            for c in story.chapters
        ],
    )


def _call(fn):
    try:
        return fn()
    except StoryNotFound as exc:
        raise HTTPException(404, "Không thấy truyện") from exc
    except StoryConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — lỗi model, không lộ key
        raise HTTPException(502, str(exc)[:500]) from exc


@router.get("/stories", response_model=StoryListOut)
def api_list_stories(db: Session = Depends(get_db)):
    items = []
    for story in list_stories(db):
        items.append(
            {
                "id": story.id,
                "title": story.title,
                "chapter_count": story.chapter_count,
                "filled_count": sum(1 for c in story.chapters if (c.text or "").strip()),
                "status": story.status,
            }
        )
    return StoryListOut(items=items)


@router.post("/stories", response_model=StoryOut, status_code=201)
def api_create_story(body: StoryCreateIn, db: Session = Depends(get_db)):
    story = _call(
        lambda: create_story(
            db,
            title=body.title,
            premise=body.premise,
            ending=body.ending,
            chapter_count=body.chapter_count,
            provider_id=body.provider_id,
            characters=[c.model_dump() for c in body.characters],
        )
    )
    return _out(story)


@router.get("/stories/{story_id}", response_model=StoryOut)
def api_get_story(story_id: int, db: Session = Depends(get_db)):
    return _out(_call(lambda: get_story(db, story_id)))


@router.patch("/stories/{story_id}", response_model=StoryOut)
def api_patch_story(story_id: int, body: StoryPatchIn, db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if "characters" in fields:
        fields["characters"] = [c if isinstance(c, dict) else c for c in fields["characters"]]
    story = _call(lambda: update_story(db, story_id, **fields))
    return _out(story)


@router.delete("/stories/{story_id}", status_code=204)
def api_delete_story(story_id: int, db: Session = Depends(get_db)):
    _call(lambda: delete_story(db, story_id))


@router.patch("/stories/{story_id}/chapters/{index}", response_model=StoryOut)
def api_patch_chapter(
    story_id: int, index: int, body: StoryChapterPatchIn, db: Session = Depends(get_db)
):
    story = _call(
        lambda: update_chapter(db, story_id, index, **body.model_dump(exclude_unset=True))
    )
    return _out(story)


@router.post("/stories/{story_id}/outline", response_model=StoryOut)
def api_outline(story_id: int, replace: bool = False, db: Session = Depends(get_db)):
    return _out(_call(lambda: generate_outline(db, story_id, replace=replace)))


@router.post("/stories/{story_id}/chapters/{index}/write", response_model=StoryOut)
def api_write_chapter(
    story_id: int, index: int, body: StoryWriteIn, db: Session = Depends(get_db)
):
    return _out(_call(lambda: write_chapter(db, story_id, index, force=body.force)))


@router.post("/stories/{story_id}/chapters/{index}/stream")
def api_stream_chapter(story_id: int, index: int, body: StoryWriteIn, db: Session = Depends(get_db)):
    provider_id, messages, saved_story_id, saved_index = _call(
        lambda: open_chapter_stream(db, story_id, index, force=body.force)
    )

    def events():
        try:
            for delta in iter_saved_chapter(provider_id, messages, saved_story_id, saved_index):
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 — đã mở stream, không đổi status được nữa
            yield f"data: {json.dumps({'error': str(exc)[:500]}, ensure_ascii=False)}\n\n"
            return
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/stories/{story_id}/write", response_model=StoryOut)
def api_write_all(story_id: int, db: Session = Depends(get_db)):
    return _out(_call(lambda: start_write_all(db, story_id)))


@router.post("/stories/{story_id}/stop", response_model=StoryOut)
def api_stop(story_id: int, db: Session = Depends(get_db)):
    return _out(_call(lambda: stop_write(db, story_id)))
