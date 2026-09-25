"""Test invariant trên entity — vd không thể force-accept 1 truyện chưa
bị reject."""
import pytest

from crawl.domain.entities import DomainError, Novel, NovelLifecycle


def _new_novel(**overrides) -> Novel:
    defaults = dict(id=1, title="Truyện test", source_key="demo_local", source_url="u")
    defaults.update(overrides)
    return Novel(**defaults)


def test_start_crawling_from_discovered_ok():
    novel = _new_novel()
    novel.start_crawling()
    assert novel.lifecycle_status == NovelLifecycle.CRAWLING


def test_start_incremental_crawl_from_fully_crawled_ok():
    novel = _new_novel(lifecycle_status=NovelLifecycle.FULLY_CRAWLED)
    novel.start_incremental_crawl()
    assert novel.lifecycle_status == NovelLifecycle.CRAWLING


def test_start_crawling_from_fully_crawled_raises():
    novel = _new_novel(lifecycle_status=NovelLifecycle.FULLY_CRAWLED)
    with pytest.raises(DomainError):
        novel.start_crawling()


def test_force_accept_requires_rejected_status():
    novel = _new_novel(lifecycle_status=NovelLifecycle.DISCOVERED)
    with pytest.raises(DomainError):
        novel.force_accept()


def test_force_accept_from_rejected_ok():
    novel = _new_novel(lifecycle_status=NovelLifecycle.REJECTED, error_message="quá dài")
    novel.force_accept()
    assert novel.lifecycle_status == NovelLifecycle.DISCOVERED
    assert novel.error_message is None


def test_advance_chapter_never_decreases():
    novel = _new_novel(last_chapter_index=5)
    novel.advance_chapter(3)  # chương cũ hơn -> không lùi lại
    assert novel.last_chapter_index == 5
    novel.advance_chapter(7)
    assert novel.last_chapter_index == 7
