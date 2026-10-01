"""Regression cho các bug review 30/9/2026: TOC trùng URL, chương failed được
lưu, novel không kẹt crawling, genre giữ `enabled`, HTTP không retry vô ích,
encoding, proxy đọc lại, cleaned cũ bị bỏ khi fetch lại, URL tay chuẩn hoá,
NovelOut đếm chương."""
from pathlib import Path

import httpx
import pytest

from crawl.application.use_cases import (
    AddManualNovelUseCase,
    CrawlNovelUseCase,
    RawTextStorage,
    RetryChapterUseCase,
)
from crawl.domain.entities import Chapter, ChapterStatus, Genre, GenreRunStatus, Novel, NovelLifecycle
from crawl.domain.ports import ScrapeError
from crawl.domain.urls import novel_url_variants
from crawl.domain.value_objects import ChapterRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)
from crawl.infrastructure.sources.base_html_source import (
    BaseHtmlSource,
    SourceConfig,
    dedupe_chapter_anchors,
)
from crawl.infrastructure.sources.content_pipeline import NonRetryableScrapeError
from crawl.infrastructure.sources.text_decode import charset_from_content_type, decode_html_bytes

_TEXT = "这是一段用于测试的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3


class _ListSource:
    key = "review_fix_test"
    name = "review fix"

    def __init__(self, refs: list[ChapterRef], fail_urls: set[str] | None = None):
        self.refs = refs
        self.fail_urls = fail_urls or set()
        self.fetched: list[str] = []

    def list_chapters(self, novel_url: str) -> list[ChapterRef]:
        return self.refs

    def fetch_chapter_content(self, chapter_url: str) -> str:
        self.fetched.append(chapter_url)
        if chapter_url in self.fail_urls:
            raise ScrapeError(f"Chương VIP — cần cookie tại {chapter_url}")
        return _TEXT

    def derive_novel_url(self, chapter_url: str) -> str | None:
        return None


def _crawl_uc(db, source, raw_dir="/tmp/review_fix_raw"):
    return CrawlNovelUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(Path(raw_dir)),
        source_resolver=lambda _k: source,
    )


def _new_novel(db, url: str, **kw) -> Novel:
    return SqlAlchemyNovelRepository(db).add(
        Novel(id=None, title="Review fix", source_key="review_fix_test", source_url=url, **kw)
    )


# ------------------------------------------------------------- TOC dedupe --

def test_dedupe_chapter_anchors_keeps_last_occurrence():
    items = [("最新 3", "https://x/3.html"), ("1", "https://x/1.html"), ("2", "https://x/2.html"),
             ("3", "http://x/3.html")]
    refs = dedupe_chapter_anchors(items)
    assert [(r.index, r.title) for r in refs] == [(1, "1"), (2, "2"), (3, "3")]


def test_sync_matches_saved_chapters_by_url_and_saves_new_one(client):  # noqa: ARG001
    """DB cũ lưu TOC còn trùng khối "最新章节" (index lệch); TOC mới đã dedupe
    — không fetch lại chương đã có theo URL, chương mới không bị nuốt vì
    index đụng row cũ."""
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = _new_novel(db, "u-dedupe-sync", lifecycle_status=NovelLifecycle.FULLY_CRAWLED)
        repo = SqlAlchemyChapterRepository(db)
        # Legacy: idx1 = bản trùng của ch3, idx2..4 = ch1..3
        legacy = [(1, "c3"), (2, "c1"), (3, "c2"), (4, "c3")]
        for idx, name in legacy:
            ch = Chapter(id=None, novel_id=novel.id, chapter_index=idx, title=name,
                         source_url=f"https://x/{name}.html")
            ch.mark_crawled(f"/tmp/review_fix_raw/legacy-{novel.id}-{idx}.txt")
            repo.add(ch)
        refs = [ChapterRef(index=i, title=f"c{i}", url=f"https://x/c{i}.html") for i in range(1, 5)]
        source = _ListSource(refs)
        result = _crawl_uc(db, source).execute(novel.id, incremental=True)
        assert result.success is True
        assert source.fetched == ["https://x/c4.html"]  # chỉ chương mới
        rows = repo.list_by_novel(novel.id)
        assert len(rows) == 5
        assert any(r.source_url == "https://x/c4.html" and r.status == ChapterStatus.CRAWLED for r in rows)
    finally:
        db.close()


# ------------------------------------------------ failed chapters persisted --

def test_failed_chapter_row_is_persisted_then_retried_on_resume(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = _new_novel(db, "u-failed-row")
        refs = [ChapterRef(index=i, title=f"c{i}", url=f"https://y/{i}") for i in range(1, 4)]
        source = _ListSource(refs, fail_urls={"https://y/2"})
        _crawl_uc(db, source).execute(novel.id)
        repo = SqlAlchemyChapterRepository(db)
        failed = repo.list_by_novel_filtered(novel.id, status="failed")
        assert [c.chapter_index for c in failed] == [2]
        assert "VIP" in (failed[0].error_message or "")

        source.fail_urls.clear()
        source.fetched.clear()
        result = _crawl_uc(db, source).execute(novel.id, incremental=True)
        assert result.chapters_crawled == 1
        assert source.fetched == ["https://y/2"]
        rows = repo.list_by_novel(novel.id)
        assert [(c.chapter_index, c.status.value) for c in rows] == [
            (1, "crawled"), (2, "crawled"), (3, "crawled"),
        ]
        novel_after = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        # (có thể còn ghi chú "Trùng nội dung" do text test dùng chung — chỉ
        # kiểm ghi chú thiếu chương đã được xoá)
        assert "Thiếu" not in (novel_after.error_message or "")
    finally:
        db.close()


# ------------------------------------------------- unexpected crash → error --

def test_unexpected_exception_marks_novel_error_not_stuck_crawling(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    class _Boom(_ListSource):
        def fetch_chapter_content(self, chapter_url: str) -> str:
            raise RuntimeError("parser exploded")

    db = SessionLocal()
    try:
        novel = _new_novel(db, "u-crash")
        source = _Boom([ChapterRef(index=1, title="c1", url="https://z/1")])
        result = _crawl_uc(db, source).execute(novel.id)
        assert result.success is False
        assert "parser exploded" in (result.error or "")
        after = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        assert after.lifecycle_status == NovelLifecycle.ERROR
        assert "parser exploded" in (after.error_message or "")
    finally:
        db.close()


# ---------------------------------------------- genre finish keeps enabled --

def test_run_state_update_does_not_overwrite_enabled(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        repo = SqlAlchemyGenreRepository(db)
        g = repo.get_or_create("review_fix_test", "g1", "G1", "https://g/1", enabled=True)
        stale: Genre = repo.get_by_id(g.id)
        stale.mark_run_started()
        repo.update_run_state(stale)

        # Người dùng tắt genre trong lúc đang quét (session khác).
        db2 = SessionLocal()
        try:
            other = SqlAlchemyGenreRepository(db2)
            fresh = other.get_by_id(g.id)
            fresh.enabled = False
            other.update(fresh)
        finally:
            db2.close()

        stale.mark_run_finished(status=GenreRunStatus.DONE, discovered=1, rejected=0, errors=0, messages=[])
        repo.update_run_state(stale)
        final = SqlAlchemyGenreRepository(SessionLocal()).get_by_id(g.id)
        assert final.enabled is False
        assert final.last_run_status == GenreRunStatus.DONE
    finally:
        db.close()


# ------------------------------------------------------------ HTTP retries --

def _html_source(handler, **cfg_kw) -> BaseHtmlSource:
    cfg = SourceConfig(
        key="review_fix_http", name="t", base_url="https://ex.test",
        request_delay_sec=0, backoff_base_sec=0.01, max_retries=2, **cfg_kw,
    )
    src = BaseHtmlSource(cfg)
    src._clients[src._current_proxy] = httpx.Client(transport=httpx.MockTransport(handler))
    return src


def test_404_is_not_retried(client):  # noqa: ARG001
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(404)

    src = _html_source(handler)
    with pytest.raises(NonRetryableScrapeError):
        src._get_soup("https://ex.test/missing")
    assert len(calls) == 1


def test_vip_page_is_not_retried(client):  # noqa: ARG001
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, html="<html><div id=content>这是VIP章节</div></html>")

    src = _html_source(handler)
    with pytest.raises(NonRetryableScrapeError):
        src._get_soup("https://ex.test/vip", check_content_blockers=True)
    assert len(calls) == 1


def test_429_honours_retry_after_then_succeeds(client, monkeypatch):  # noqa: ARG001
    calls = []
    waits = []

    def handler(request):
        calls.append(request.url)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, html="<html><h1>ok</h1></html>")

    import platform_.run_cancel

    monkeypatch.setattr(platform_.run_cancel, "interruptible_sleep", lambda s: waits.append(s))
    src = _html_source(handler)
    soup = src._get_soup("https://ex.test/limited")
    assert soup.select_one("h1").get_text() == "ok"
    assert len(calls) == 2
    assert waits and waits[0] == pytest.approx(7.0)


# ---------------------------------------------------------------- encoding --

def test_gbk_page_without_header_charset_uses_meta_charset(client):  # noqa: ARG001
    body = '<html><head><meta charset="gbk"></head><body><h1>第一章 测试</h1></body></html>'.encode("gbk")

    def handler(request):
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    src = _html_source(handler)
    assert src._get_soup("https://ex.test/gbk").select_one("h1").get_text() == "第一章 测试"


def test_charset_helpers_map_gbk_to_gb18030():
    assert charset_from_content_type("text/html; charset=GBK") == "gb18030"
    assert charset_from_content_type("text/html") is None
    assert decode_html_bytes("中文".encode("gb18030"), preferred="gb2312") == "中文"


# ------------------------------------------------------------------- proxy --

def test_proxy_is_reread_after_setting_changes(client, monkeypatch):  # noqa: ARG001
    from crawl.infrastructure.sources import base_html_source as mod

    current = {"proxy": None}
    monkeypatch.setattr(mod, "get_a_proxy", lambda source_key=None: current["proxy"])
    src = BaseHtmlSource(SourceConfig(key="review_fix_proxy", name="t", base_url="https://ex.test"))
    assert src._proxy_url == ""
    first = src._client
    current["proxy"] = "http://127.0.0.1:18080"
    src._proxy_checked_at = 0.0  # hết TTL
    assert src._proxy_url == "http://127.0.0.1:18080"
    assert src._client is not first


# ------------------------------------------ retry chapter drops old cleaned --

def test_retry_chapter_discards_stale_cleaned(client, tmp_path):  # noqa: ARG001
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        storage = RawTextStorage(tmp_path / "raw")
        novel = _new_novel(db, "u-retry-cleaned")
        raw_path = storage.save(novel.id, 1, "old raw")
        storage.save_cleaned(raw_path, "old cleaned")
        ch = Chapter(id=None, novel_id=novel.id, chapter_index=1, title="c1", source_url="https://w/1")
        ch.mark_crawled(raw_path)
        ch.reviewed = True
        ch = SqlAlchemyChapterRepository(db).add(ch)

        uc = RetryChapterUseCase(
            chapter_repo=SqlAlchemyChapterRepository(db),
            novel_repo=SqlAlchemyNovelRepository(db),
            storage=storage,
            source_resolver=lambda _k: _ListSource([]),
        )
        assert uc.execute(ch.id).success is True
        assert storage.has_cleaned(raw_path) is False
        assert storage.read_preferred(raw_path) == (_TEXT, "raw")
        assert SqlAlchemyChapterRepository(db).get_by_id(ch.id).reviewed is False
    finally:
        db.close()


# ------------------------------------------------------- manual URL lookup --

def test_novel_url_variants_cover_scheme_slash_and_host():
    v = novel_url_variants(" http://m.example.com/book/1/#top ", base_url="https://www.example.com")
    assert v[0] == "http://m.example.com/book/1/"
    assert "https://www.example.com/book/1/" in v
    assert "https://example.com/book/1" in v
    assert novel_url_variants("/tmp/demo") == ["/tmp/demo"]


def test_add_manual_detects_existing_novel_with_url_variant(client):  # noqa: ARG001
    from platform_.db import SessionLocal

    class _Src(_ListSource):
        class cfg:  # noqa: N801
            base_url = "https://www.variant.test"
            content_locale = "zh"

    db = SessionLocal()
    try:
        existing = _new_novel(db, "https://www.variant.test/book/9/")
        uc = AddManualNovelUseCase(
            novel_repo=SqlAlchemyNovelRepository(db),
            crawl_novel_use_case=_crawl_uc(db, None),
            source_resolver=lambda _k: _Src([]),
        )
        result = uc.execute("review_fix_test", "http://www.variant.test/book/9#frag", start_crawl=False)
        assert result.success is False
        assert result.novel_id == existing.id
    finally:
        db.close()


# --------------------------------------------------------- NovelOut counts --

def test_novel_out_includes_chapter_counts_and_timestamps(client):
    from platform_.db import SessionLocal

    db = SessionLocal()
    try:
        novel = _new_novel(db, "u-counts")
        repo = SqlAlchemyChapterRepository(db)
        for idx, ok in ((1, True), (2, True), (3, False)):
            ch = Chapter(id=None, novel_id=novel.id, chapter_index=idx, title=f"c{idx}", source_url=f"c{idx}")
            if ok:
                ch.mark_crawled(f"/tmp/review_fix_raw/c{idx}.txt")
            else:
                ch.mark_failed("x")
            repo.add(ch)
    finally:
        db.close()

    data = client.get(f"/api/crawl/novels/{novel.id}").json()
    assert data["crawled_chapters"] == 2
    assert data["failed_chapters"] == 1
    assert data["created_at"] and data["updated_at"]
    listed = client.get("/api/crawl/novels", params={"source_key": "review_fix_test", "limit": 100}).json()
    row = next(n for n in listed["items"] if n["id"] == novel.id)
    assert (row["crawled_chapters"], row["failed_chapters"]) == (2, 1)
