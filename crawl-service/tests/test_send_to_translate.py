"""send-to-translate — mock HTTP tới translate-service."""
from unittest.mock import MagicMock, patch

from crawl.application.use_cases import RawTextStorage
from crawl.domain.entities import Chapter, ChapterStatus, Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyNovelRepository,
)
from platform_.config import config
from platform_.db import SessionLocal


def test_send_to_translate_mocked(client):
    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(
                id=None,
                source_key="demo_local",
                source_url="http://example/demo-send",
                title="Send Demo",
                genre_id=None,
                is_manual=True,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
                last_chapter_index=1,
                total_chapters=1,
            )
        )
        storage = RawTextStorage(config.raw_dir)
        raw_path = storage.save(novel.id, 1, "Hello chapter body for translate.")
        storage.save_cleaned(raw_path, "Hello chapter body for translate.")
        SqlAlchemyChapterRepository(db).add(
            Chapter(
                id=None,
                novel_id=novel.id,
                chapter_index=1,
                title="Ch1",
                source_url="http://example/c1",
                raw_path=raw_path,
                status=ChapterStatus.CRAWLED,
                reviewed=True,
            )
        )
        nid = novel.id
    finally:
        db.close()

    mock_resp_work = MagicMock()
    mock_resp_work.status_code = 200
    mock_resp_work.json.return_value = {
        "id": 99,
        "external_id": f"crawl:novel:{nid}",
        "source_type": "crawl_handoff",
        "variants": [{"id": 7}],
    }
    mock_resp_job = MagicMock()
    mock_resp_job.status_code = 202
    mock_resp_job.json.return_value = {"id": 55}

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = [mock_resp_work, mock_resp_job]

    with patch("crawl.application.send_to_translate.httpx.Client", return_value=mock_client):
        r = client.post(
            f"/api/crawl/novels/{nid}/send-to-translate",
            json={"require_cleaned": True, "start_job": True},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["work_id"] == 99
    assert data["variant_id"] == 7
    assert data["job_id"] == 55
    assert data["lifecycle_status"] == "translating"
    assert data["translate_path"] == "/translate/99"
