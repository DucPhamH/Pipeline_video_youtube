"""API làm mượt rule 1 novel."""
from pathlib import Path

from crawl.application.use_cases import RawTextStorage
from crawl.domain.entities import Chapter, ChapterStatus, Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal


def test_smooth_novel_endpoint(client):
    db = SessionLocal()
    storage = RawTextStorage(config.raw_dir)
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Smooth Test",
                source_key="demo_local",
                source_url="http://demo.local/smooth-1",
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
                last_chapter_index=1,
                total_chapters=1,
            )
        )
        raw = (
            "他走在路上，看见前方有一道光。\n"
            "请收藏本站推荐给朋友\n"
            "心里很害怕，不知道该怎么办。"
        )
        path = storage.save(novel.id, 1, raw)
        chapter_repo.add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=1,
                title="第一章",
                source_url="http://demo.local/ch1",
                raw_path=path,
                status=ChapterStatus.CRAWLED,
            )
        )
        nid = novel.id
    finally:
        db.close()

    r = client.post(f"/api/crawl/novels/{nid}/smooth")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["chapters_smoothed"] == 1
    assert body["removed_lines"] >= 1
    assert len(body["chapter_ids"]) == 1

    # Chỉ 1 chương — gọi lại với chapter_ids rỗng / all vẫn OK
    r2 = client.post(
        f"/api/crawl/novels/{nid}/smooth",
        json={"chapter_ids": body["chapter_ids"]},
    )
    assert r2.status_code == 200
    assert r2.json()["chapters_smoothed"] == 1

    cleaned = Path(storage.cleaned_path_for(path))
    assert cleaned.is_file()
    text = cleaned.read_text(encoding="utf-8")
    assert "请收藏" not in text
    assert "他走在路上" in text

    listed = client.get(f"/api/crawl/novels/{nid}/chapters", params={"limit": 5}).json()
    cid = listed["items"][0]["id"]
    content = client.get(f"/api/crawl/chapters/{cid}/content")
    assert content.status_code == 200
    body_c = content.json()
    assert body_c["content_source"] == "cleaned"
    assert "请收藏" not in (body_c["content"] or "")
    assert body_c["raw_content"] is not None
    assert "请收藏" in body_c["raw_content"]
    assert body_c["cleaned_content"] is not None
    assert "请收藏" not in body_c["cleaned_content"]

    discarded = client.delete(f"/api/crawl/chapters/{cid}/cleaned")
    assert discarded.status_code == 200, discarded.text
    body_d = discarded.json()
    assert body_d["success"] is True
    assert body_d["has_cleaned"] is False
    assert body_d["content_source"] == "raw"
    assert "请收藏" in (body_d["content"] or "")
    assert not cleaned.is_file()

    again = client.get(f"/api/crawl/chapters/{cid}/content")
    assert again.json()["content_source"] == "raw"
    assert again.json()["has_cleaned"] is False
