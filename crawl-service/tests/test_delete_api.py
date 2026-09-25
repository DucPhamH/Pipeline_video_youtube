"""API xóa novel / chapter + file raw/cleaned."""
from pathlib import Path

from crawl.application.use_cases import RawTextStorage
from crawl.domain.entities import Chapter, ChapterStatus, Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal


def test_delete_novel_and_chapter(client):
    db = SessionLocal()
    storage = RawTextStorage(config.raw_dir)
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        chapter_repo = SqlAlchemyChapterRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Delete Me",
                source_key="demo_local",
                source_url="http://demo.local/delete-1",
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
                last_chapter_index=2,
                total_chapters=2,
            )
        )
        path1 = storage.save(novel.id, 1, "chương một nội dung đủ dài để test.\n")
        path2 = storage.save(novel.id, 2, "chương hai nội dung đủ dài để test.\n")
        storage.save_cleaned(path1, "cleaned one\n")
        ch1 = chapter_repo.add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=1,
                title="Ch 1",
                source_url="http://demo.local/c1",
                raw_path=path1,
                status=ChapterStatus.CRAWLED,
            )
        )
        chapter_repo.add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=2,
                title="Ch 2",
                source_url="http://demo.local/c2",
                raw_path=path2,
                status=ChapterStatus.CRAWLED,
            )
        )
        nid = novel.id
        cid1 = ch1.id
    finally:
        db.close()

    # Xóa 1 chương
    r = client.delete(f"/api/crawl/chapters/{cid1}")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert not Path(path1).is_file()
    assert not Path(storage.cleaned_path_for(path1)).is_file()
    assert Path(path2).is_file()

    listed = client.get(f"/api/crawl/novels/{nid}/chapters", params={"limit": 10}).json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["chapter_index"] == 2

    novel_body = client.get(f"/api/crawl/novels/{nid}").json()
    assert novel_body["last_chapter_index"] == 2

    # Xóa cả truyện
    r2 = client.delete(f"/api/crawl/novels/{nid}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["success"] is True
    assert client.get(f"/api/crawl/novels/{nid}").status_code == 404
    assert not Path(path2).is_file()
    assert not (Path(config.raw_dir) / str(nid)).is_dir()


def test_delete_novel_blocked_while_crawling(client):
    db = SessionLocal()
    try:
        novel_repo = SqlAlchemyNovelRepository(db)
        novel = novel_repo.add(
            Novel(
                id=None,
                title="Crawling",
                source_key="demo_local",
                source_url="http://demo.local/delete-crawl",
                lifecycle_status=NovelLifecycle.CRAWLING,
            )
        )
        nid = novel.id
    finally:
        db.close()

    r = client.delete(f"/api/crawl/novels/{nid}")
    assert r.status_code == 400
    assert client.get(f"/api/crawl/novels/{nid}").status_code == 200
