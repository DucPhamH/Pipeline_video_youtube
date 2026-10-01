"""Domain + API lifecycle callback cho translate."""
from crawl.domain.entities import DomainError, Novel, NovelLifecycle


def _novel(**kwargs) -> Novel:
    defaults = dict(
        id=1,
        source_key="demo",
        source_url="http://x",
        title="T",
        genre_id=None,
        is_manual=True,
        lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
    )
    defaults.update(kwargs)
    return Novel(**defaults)


def test_mark_translating_from_fully_crawled():
    n = _novel()
    n.mark_translating()
    assert n.lifecycle_status == NovelLifecycle.TRANSLATING


def test_mark_ready_for_video():
    n = _novel(lifecycle_status=NovelLifecycle.TRANSLATING)
    n.mark_ready_for_video()
    assert n.lifecycle_status == NovelLifecycle.READY_FOR_VIDEO


def test_mark_translating_from_discovered_raises():
    n = _novel(lifecycle_status=NovelLifecycle.DISCOVERED)
    try:
        n.mark_translating()
        raise AssertionError("expected DomainError")
    except DomainError:
        pass


def test_translate_lifecycle_endpoint(client):
    from platform_.db import SessionLocal
    from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository

    db = SessionLocal()
    try:
        novel = SqlAlchemyNovelRepository(db).add(
            Novel(
                id=None,
                source_key="demo_local",
                source_url="http://example/demo",
                title="Lifecycle Demo",
                genre_id=None,
                is_manual=True,
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
            )
        )
        db.commit()
        nid = novel.id
    finally:
        db.close()

    r = client.post(
        f"/api/crawl/novels/{nid}/translate-lifecycle",
        json={"status": "translating"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "translating"

    r = client.post(
        f"/api/crawl/novels/{nid}/translate-lifecycle",
        json={"status": "ready_for_video"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle_status"] == "ready_for_video"
