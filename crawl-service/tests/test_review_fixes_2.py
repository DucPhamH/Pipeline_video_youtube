"""Regression cho review 01/10/2026: sync theo URL (không theo
last_chapter_index), toc_order, dedupe TOC, cache httpx, decode strict, FK vs
UNIQUE, Retry-After, demo_local, SSRF/cookie, mask cookie, allow-list
settings, token auth, send-to-translate, challenge trang danh sách, smooth
không đè chương đã review, khoá crawl-novel trong genre scan, webhook,
progress novel."""
from pathlib import Path

import httpx
import pytest

from crawl.application.use_cases import (
    CrawlGenreUseCase,
    CrawlNovelUseCase,
    NovelExportUseCase,
    RawTextStorage,
    SmoothNovelUseCase,
    toc_has_unsaved_chapters,
)
from crawl.domain.entities import Chapter, ChapterStatus, Novel, NovelLifecycle
from crawl.domain.ports import ScrapeError
from crawl.domain.urls import host_matches_source
from crawl.domain.value_objects import ChapterRef, NovelRef
from crawl.infrastructure.persistence.repositories import (
    SqlAlchemyChapterRepository,
    SqlAlchemyGenreRepository,
    SqlAlchemyNovelRepository,
)
from crawl.infrastructure.sources.base_html_source import BaseHtmlSource, SourceConfig, dedupe_chapter_anchors
from crawl.infrastructure.sources.content_pipeline import ChallengeError
from crawl.infrastructure.sources.fetch_guard import BlockedUrlError, assert_public_url
from crawl.infrastructure.sources.text_decode import decode_html_bytes

_TEXT = "这是第二轮评审测试用的中文内容,长度足够长,汉字比例也足够高,可以通过内容校验。" * 3
SK = "review2_test"


class _Src:
    key = SK
    name = "review2"
    cfg = type("Cfg", (), {"base_url": "https://r2.test", "content_locale": "zh"})()

    def __init__(self, refs, novels=None):
        self.refs = refs
        self.novels = novels or []
        self.fetched: list[str] = []

    def list_genre_novels_page(self, url, page):
        return self.novels if page == 1 else []

    def list_chapters(self, novel_url):
        return self.refs

    def fetch_chapter_content(self, url):
        self.fetched.append(url)
        return _TEXT

    def derive_novel_url(self, url):
        return None


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()


def _crawl_uc(db, source, raw_dir):
    return CrawlNovelUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        chapter_repo=SqlAlchemyChapterRepository(db),
        storage=RawTextStorage(Path(raw_dir)),
        source_resolver=lambda _k: source,
    )


def _genre_uc(db, source, raw_dir):
    return CrawlGenreUseCase(
        novel_repo=SqlAlchemyNovelRepository(db),
        genre_repo=SqlAlchemyGenreRepository(db),
        crawl_novel_use_case=_crawl_uc(db, source, raw_dir),
        source_resolver=lambda _k: source,
        get_scan_window=lambda _k: 5,
        get_max_chapters_per_story=lambda _k: 100,
        get_completion_filter=lambda _k: "any",
    )


def _add_rows(db, novel_id, rows, raw_dir):
    repo = SqlAlchemyChapterRepository(db)
    storage = RawTextStorage(Path(raw_dir))
    for idx, url in rows:
        ch = Chapter(
            id=None, novel_id=novel_id, chapter_index=idx, title=url.rsplit("/", 1)[-1], source_url=url
        )
        ch.mark_crawled(storage.save(novel_id, idx, _TEXT + url))
        repo.add(ch)


# ---------------------------------------------------- 1. sync by URL keys --

def test_toc_has_unsaved_chapters_by_url_not_index():
    saved = [Chapter(id=1, novel_id=1, chapter_index=i, title="", source_url=f"https://a/{i}",
                     status=ChapterStatus.CRAWLED) for i in (1, 2, 3)]
    toc = [ChapterRef(index=i, title="", url=f"https://a/{i}") for i in (1, 2, 3)]
    assert toc_has_unsaved_chapters(toc, saved) is False
    assert toc_has_unsaved_chapters(toc + [ChapterRef(index=4, title="", url="https://a/4")], saved) is True
    # Site đổi domain: không URL nào khớp -> so số chương đã xong
    moved = [ChapterRef(index=i, title="", url=f"https://b/{i}") for i in (1, 2, 3)]
    assert toc_has_unsaved_chapters(moved, saved) is False


def test_genre_sync_finds_new_chapter_despite_inflated_last_index(client, tmp_path):  # noqa: ARG001
    """last_chapter_index cũ bị thổi phồng (TOC trùng khối 最新章节) = 5 nhưng
    TOC đã dedupe chỉ còn 4 chương, chương 4 mới — vẫn phải sync."""
    db = _db()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(SK, "g-sync", "G", "https://r2.test/list")
        novel = SqlAlchemyNovelRepository(db).add(Novel(
            id=None, title="Inflated", source_key=SK, source_url="https://r2.test/book/1",
            last_chapter_index=5, total_chapters=5, lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
        ))
        _add_rows(db, novel.id, [(1, "https://r2.test/c3"), (2, "https://r2.test/c1"),
                                 (3, "https://r2.test/c2"), (4, "https://r2.test/c3"),
                                 (5, "https://r2.test/c0")], tmp_path)
        refs = [ChapterRef(index=i, title=f"c{i}", url=f"https://r2.test/c{i}") for i in range(1, 5)]
        ref = NovelRef(title="Inflated", url="https://r2.test/book/1", latest_chapter_title="")
        src = _Src(refs, novels=[ref])
        result = _genre_uc(db, src, tmp_path).execute(genre.id)
        assert result.synced == 1
        assert src.fetched == ["https://r2.test/c4"]
        after = SqlAlchemyNovelRepository(db).get_by_id(novel.id)
        # next-free index (6) không được đẩy last_chapter_index vượt TOC
        assert after.last_chapter_index == 4
        # 2. thứ tự đọc theo toc_order: c4 (lưu ở index 6) đứng sau c3, không cuối sau c0
        rows = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        order = [r.source_url.rsplit("/", 1)[-1] for r in rows]
        assert order.index("c4") > order.index("c3")
        assert order[:3] == ["c1", "c2", "c3"] or order[:4] == ["c1", "c2", "c3", "c3"]
    finally:
        db.close()


# ------------------------------------------------ 2. toc_order in exports --

def test_mid_toc_insert_sorted_by_toc_order_in_export_and_listing(client, tmp_path):
    db = _db()
    try:
        novel = SqlAlchemyNovelRepository(db).add(Novel(
            id=None, title="MidInsert", source_key=SK, source_url="https://r2.test/book/mid",
            lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
        ))
        _add_rows(db, novel.id, [(1, "https://r2.test/m1"), (2, "https://r2.test/m3")], tmp_path)
        # Site chèn m2 vào giữa: TOC mới m1, m2, m3 — m2 lưu ở index trống (3)
        refs = [ChapterRef(index=i, title=f"m{i}", url=f"https://r2.test/m{i}") for i in (1, 2, 3)]
        res = _crawl_uc(db, _Src(refs), tmp_path).execute(novel.id, incremental=True)
        assert res.success
        rows = SqlAlchemyChapterRepository(db).list_by_novel(novel.id)
        assert [r.title for r in rows] == ["m1", "m2", "m3"]
        assert [r.chapter_index for r in rows] == [1, 3, 2]  # chapter_index giữ làm định danh
        export_rows = NovelExportUseCase(
            SqlAlchemyNovelRepository(db), SqlAlchemyChapterRepository(db), RawTextStorage(tmp_path)
        )._rows(novel.id)
        assert [r.title for r in export_rows] == ["m1", "m2", "m3"]
    finally:
        db.close()
    listed = client.get(f"/api/crawl/novels/{novel.id}/chapters").json()["items"]
    assert [c["title"] for c in listed] == ["m1", "m2", "m3"]
    assert [c["toc_order"] for c in listed] == [1, 2, 3]


# ----------------------------------------------------------- 3. dedupe --

def test_dedupe_keeps_first_when_duplicate_not_in_leading_block():
    items = [("1", "https://x/1"), ("2", "https://x/2"), ("3", "https://x/3"),
             ("2 again", "https://x/2"), ("4", "https://x/4")]
    assert [r.title for r in dedupe_chapter_anchors(items)] == ["1", "2", "3", "4"]


def test_dedupe_drops_only_leading_latest_block():
    items = [("最新 4", "https://x/4"), ("最新 5", "https://x/5"),
             ("1", "https://x/1"), ("2", "https://x/2"), ("4", "https://x/4"), ("5", "https://x/5")]
    assert [r.title for r in dedupe_chapter_anchors(items)] == ["1", "2", "4", "5"]


# --------------------------------------------------- 5. httpx client cache --

def test_stale_proxy_clients_are_closed(client, monkeypatch):  # noqa: ARG001
    from crawl.infrastructure.sources import base_html_source as mod

    current = {"proxy": "http://p1:1"}
    monkeypatch.setattr(mod, "get_a_proxy", lambda source_key=None: current["proxy"])
    src = BaseHtmlSource(SourceConfig(key="r2_proxy", name="t", base_url="https://r2.test"))
    first = src._client
    src._client_last_used["http://p1:1"] -= 10_000  # idle lâu
    current["proxy"] = "http://p2:2"
    src._proxy_checked_at = 0.0
    second = src._client
    assert second is not first
    assert first.is_closed
    assert set(src._clients) == {"http://p2:2"}


# --------------------------------------------------------- 6. strict decode --

def test_declared_charset_wrong_falls_back_to_detection():
    body = ("<html><body>" + "第一章 测试内容，这是简体中文。" * 20 + "</body></html>").encode("utf-8")
    text = decode_html_bytes(body, preferred="ascii")
    assert "第一章" in text
    assert decode_html_bytes("中文".encode("gb18030"), preferred="gbk") == "中文"


# ------------------------------------------------------- 7. FK vs UNIQUE --

def test_non_unique_integrity_error_is_not_duplicate():
    from sqlalchemy.exc import IntegrityError

    from crawl.infrastructure.persistence.repositories import _is_unique_violation

    assert _is_unique_violation(IntegrityError("x", {}, Exception("UNIQUE constraint failed: chapters.x")))
    assert not _is_unique_violation(IntegrityError("x", {}, Exception("FOREIGN KEY constraint failed")))


# ------------------------------------------------------------ 8. Retry-After --

def _mock_source(handler, **kw):
    cfg = SourceConfig(key="r2_http", name="t", base_url="https://r2.test", request_delay_sec=0,
                       backoff_base_sec=0.01, max_retries=3, **kw)
    src = BaseHtmlSource(cfg)
    src._clients[src._current_proxy] = httpx.Client(transport=httpx.MockTransport(handler))
    return src


def test_retry_after_total_wait_is_capped(client, monkeypatch):  # noqa: ARG001
    import platform_.run_cancel

    waits: list[float] = []
    monkeypatch.setattr(platform_.run_cancel, "interruptible_sleep", lambda s: waits.append(s))
    src = _mock_source(lambda req: httpx.Response(429, headers={"Retry-After": "100"}))
    with pytest.raises(ScrapeError):
        src._get_soup("https://r2.test/limited")
    assert sum(waits) <= 180.0 + 1e-6


def test_retry_wait_stops_when_cancelled():
    from platform_.run_cancel import CancelledDuringWait, cancel_scope, interruptible_sleep

    with cancel_scope(lambda: True):
        with pytest.raises(CancelledDuringWait):
            interruptible_sleep(60)


# ---------------------------------------------------- 9. demo_local paths --

def test_demo_local_rejects_paths_outside_fixtures(client):
    r = client.post("/api/crawl/dry-run", json={"source_key": "demo_local", "url": "/etc", "mode": "content"})
    body = r.json()
    assert "passwd" not in (body.get("content_preview") or "")
    assert body.get("content_length") in (0, None)
    r = client.post(
        "/api/crawl/dry-run", json={"source_key": "demo_local", "url": "/etc/hostname", "mode": "content"}
    )
    assert not (r.json().get("content_preview") or "")


def test_demo_source_only_registered_when_flag_on():
    from crawl.infrastructure.sources.registry import SOURCES
    from platform_.config import config

    assert config.crawl_enable_demo_source is True  # conftest bật
    assert "demo_local" in SOURCES


# ------------------------------------------------------ 10. SSRF / cookie --

def test_host_matching_variants():
    assert host_matches_source("https://m.bqgxs.com/book/1", "https://www.bqgxs.com")
    assert host_matches_source("http://wap.bqgxs.com/x", "https://www.bqgxs.com")
    assert host_matches_source("https://mirror.example/x", "https://www.bqgxs.com", ["mirror.example"])
    assert not host_matches_source("https://evil.com/bqgxs.com", "https://www.bqgxs.com")
    assert not host_matches_source("https://bqgxs.com.evil.com/", "https://www.bqgxs.com")


def test_private_ip_fetch_is_blocked():
    for url in ("http://127.0.0.1/", "http://localhost:8000/x", "http://169.254.169.254/latest",
                "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd"):
        with pytest.raises(BlockedUrlError):
            assert_public_url(url)


def test_add_and_dry_run_reject_foreign_host(client):
    r = client.post(
        "/api/crawl/dry-run",
        json={"source_key": "bqgxs_com", "url": "http://127.0.0.1:8000/", "mode": "chapters"},
    )
    assert r.json()["ok"] is False and "không thuộc site" in r.json()["error"]
    r = client.post("/api/crawl/novels", json={"source_key": "bqgxs_com", "url": "https://evil.example/book/1"})
    assert r.json()["success"] is False and "không thuộc site" in r.json()["error"]


def test_cookie_only_sent_to_matching_host(client, monkeypatch):  # noqa: ARG001
    seen: dict[str, str | None] = {}

    def handler(req):
        seen[req.url.host] = req.headers.get("cookie")
        return httpx.Response(200, html="<html><h1>ok</h1></html>")

    src = _mock_source(handler)
    monkeypatch.setattr(
        src, "_apply_user_session", lambda: setattr(src, "_session_cookie_header", "sid=SECRET")
    )
    src._get_soup("https://www.r2.test/a")
    src._get_soup("https://other.test/b")
    assert seen["www.r2.test"] == "sid=SECRET"
    assert seen["other.test"] is None
    # Hook trên client thật cũng gỡ Cookie khi host lạ (vd redirect)
    req = httpx.Request("GET", "https://other.test/x", headers={"Cookie": "sid=SECRET"})
    src._guard_request(req)
    assert "cookie" not in req.headers


# ------------------------------------------------------- 11. mask cookies --

def test_settings_and_session_never_return_cookie_values(client):
    client.put("/api/crawl/sites/bqgxs_com/session", json={"cookie_header": "sid=TOPSECRET; uid=7"})
    try:
        values = client.get("/api/crawl/settings").json()["values"]
        assert "TOPSECRET" not in str(values)
        masked = values["crawl.session_cookie.bqgxs_com"]
        assert masked["has_cookie"] is True and "sid" in masked["hint"]
        sess = client.get("/api/crawl/sites/bqgxs_com/session").json()
        assert "TOPSECRET" not in str(sess)
        assert sess["has_cookie"] is True
    finally:
        client.put("/api/crawl/sites/bqgxs_com/session", json={"cookie_header": ""})


# --------------------------------------------------- 12. settings allow-list --

def test_patch_settings_rejects_unknown_key_and_bad_types(client):
    assert client.patch("/api/crawl/settings", json={"values": {"evil.key": 1}}).status_code == 422
    bad = {"values": {"crawl.scan_window.bqgxs_com": "9"}}
    assert client.patch("/api/crawl/settings", json=bad).status_code == 422
    bad = {"values": {"crawl.narration_filter.bqgxs_com": "x"}}
    assert client.patch("/api/crawl/settings", json=bad).status_code == 422
    bad = {"values": {"crawl.session_cookie.bqgxs_com": "a=1"}}
    assert client.patch("/api/crawl/settings", json=bad).status_code == 422
    for bad in ("ftp://hook", "http://127.0.0.1:9000/hook", "http://192.168.1.2/x"):
        r = client.patch("/api/crawl/settings", json={"values": {"notify.webhook_url": bad}})
        assert r.status_code == 422, bad
    ok = client.patch("/api/crawl/settings", json={"values": {"notify.webhook_url": ""}})
    assert ok.status_code == 200


# ------------------------------------------------------------- 13. auth --

def test_token_auth_when_configured(client, monkeypatch):
    from platform_.config import config

    monkeypatch.setattr(config, "folio_api_token", "s3cret")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/crawl/sites").status_code == 401
    assert client.get("/api/crawl/sites", headers={"X-Folio-Token": "nope"}).status_code == 401
    assert client.get("/api/crawl/sites", headers={"X-Folio-Token": "s3cret"}).status_code == 200
    assert client.get("/api/crawl/sites", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/crawl/sites?token=s3cret").status_code == 200
    # ?token chỉ cho GET; callback translate-lifecycle cũng đòi token
    assert client.post("/api/crawl/novels/1/translate-lifecycle?token=s3cret",
                       json={"status": "translating"}).status_code == 401
    pre = client.options("/api/crawl/sites", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "x-folio-token",
    })
    assert pre.status_code == 200
    assert "x-folio-token" in pre.headers.get("access-control-allow-headers", "").lower()


def test_no_token_configured_allows_everything(client):
    assert client.get("/api/crawl/sites").status_code == 200


# ------------------------------------------------- 14. send-to-translate --

def _translate_novel(db, tmp_path, status=NovelLifecycle.FULLY_CRAWLED):
    novel = SqlAlchemyNovelRepository(db).add(Novel(
        id=None, title="ToTranslate", source_key=SK, source_url=f"https://r2.test/book/t{tmp_path.name}",
        lifecycle_status=status,
    ))
    _add_rows(db, novel.id, [(1, f"https://r2.test/t{tmp_path.name}/1")], tmp_path)
    failed = Chapter(id=None, novel_id=novel.id, chapter_index=2, title="t2", source_url="https://r2.test/t2")
    failed.mark_failed("VIP")
    SqlAlchemyChapterRepository(db).add(failed)
    return novel


def _patch_translate_http(monkeypatch, handler, seen_headers):
    from crawl.application import send_to_translate as mod

    real = httpx.Client

    def factory(*args, headers=None, **kw):
        seen_headers.append(dict(headers or {}))
        kw.pop("timeout", None)
        return real(transport=httpx.MockTransport(handler), headers=headers)

    monkeypatch.setattr(mod.httpx, "Client", factory)


def test_send_to_translate_job_failure_still_hands_off(client, tmp_path, monkeypatch):
    from platform_.config import config

    monkeypatch.setattr(config, "folio_api_token", "tok")
    db = _db()
    try:
        novel = _translate_novel(db, tmp_path)
    finally:
        db.close()

    def handler(req):
        if req.url.path.endswith("/from-crawl"):
            return httpx.Response(200, json={"id": 77, "external_id": "x", "variants": [{"id": 5}]})
        return httpx.Response(500, text="boom")

    seen: list[dict] = []
    _patch_translate_http(monkeypatch, handler, seen)
    r = client.post(f"/api/crawl/novels/{novel.id}/send-to-translate",
                    json={"require_cleaned": False, "start_job": True}, headers={"X-Folio-Token": "tok"})
    assert r.status_code == 502
    assert "Work #77" in r.json()["detail"]
    assert seen and seen[0].get("X-Folio-Token") == "tok"
    after = client.get(f"/api/crawl/novels/{novel.id}", headers={"X-Folio-Token": "tok"}).json()
    assert after["lifecycle_status"] == "translating"


def test_send_to_translate_warns_on_failed_chapters(client, tmp_path, monkeypatch):
    db = _db()
    try:
        novel = _translate_novel(db, tmp_path)
    finally:
        db.close()

    def handler(req):
        if req.url.path.endswith("/from-crawl"):
            return httpx.Response(200, json={"id": 78, "external_id": "x", "variants": [{"id": 6}]})
        return httpx.Response(200, json={"id": 9})

    _patch_translate_http(monkeypatch, handler, [])
    r = client.post(f"/api/crawl/novels/{novel.id}/send-to-translate", json={"require_cleaned": False})
    assert r.status_code == 200
    assert any("chương lỗi" in w for w in r.json()["warnings"])


# --------------------------------------------- 15. challenge on listing --

def test_challenge_on_listing_page_reports_error(client):  # noqa: ARG001
    cf = (
        "<html><head><title>Just a moment...</title></head>"
        "<body>cloudflare challenges.cloudflare.com</body></html>"
    )
    src = _mock_source(lambda req: httpx.Response(200, html=cf), paginate_list_url=lambda u, p: f"{u}?p={p}")
    with pytest.raises(ChallengeError):
        src._get_soup("https://r2.test/list")
    # Trang 2 bị challenge KHÔNG được coi là "hết danh sách" (rỗng)
    with pytest.raises(ChallengeError):
        src.list_genre_novels_page("https://r2.test/list", 2)
    with pytest.raises(ChallengeError):
        src.list_chapters("https://r2.test/book")


def test_genre_scan_hitting_challenge_reports_error(client, tmp_path):  # noqa: ARG001
    from crawl.domain.entities import GenreRunStatus

    class _CfSrc(_Src):
        def list_genre_novels_page(self, url, page):
            raise ChallengeError(f"[{SK}] Cloudflare/challenge tại {url}")

    db = _db()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(SK, "g-cf", "G", "https://r2.test/list-cf")
        result = _genre_uc(db, _CfSrc([]), tmp_path).execute(genre.id)
        assert result.stopped_as_error is True
        assert any("Cloudflare" in m for m in result.messages)
        assert SqlAlchemyGenreRepository(db).get_by_id(genre.id).last_run_status == GenreRunStatus.ERROR
    finally:
        db.close()


# ------------------------------------------------------------- 16. smooth --

def test_smooth_skips_reviewed_unless_forced(client, tmp_path):  # noqa: ARG001
    db = _db()
    try:
        novel = SqlAlchemyNovelRepository(db).add(Novel(
            id=None, title="Smooth", source_key=SK, source_url="https://r2.test/book/s",
            lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
        ))
        _add_rows(db, novel.id, [(1, "https://r2.test/s1"), (2, "https://r2.test/s2")], tmp_path)
        repo = SqlAlchemyChapterRepository(db)
        storage = RawTextStorage(tmp_path)
        edited = repo.list_by_novel(novel.id)[0]
        storage.save_cleaned(edited.raw_path, "BẢN SỬA TAY")
        edited.mark_reviewed()
        repo.update(edited)
        uc = SmoothNovelUseCase(SqlAlchemyNovelRepository(db), repo, storage)
        res = uc.execute(novel.id)
        assert res.chapters_smoothed == 1 and res.chapters_protected == 1
        assert storage.read_preferred(edited.raw_path)[0] == "BẢN SỬA TAY"
        assert repo.get_by_id(edited.id).reviewed is True
        res = uc.execute(novel.id, force=True)
        assert res.chapters_smoothed == 2
        assert storage.read_preferred(edited.raw_path)[0] != "BẢN SỬA TAY"
    finally:
        db.close()


# -------------------------------------------------- 17. lock in genre scan --

def test_genre_sync_skips_novel_locked_by_other_crawl(client, tmp_path):  # noqa: ARG001
    from platform_.locks import release, try_acquire

    db = _db()
    try:
        genre = SqlAlchemyGenreRepository(db).get_or_create(SK, "g-lock", "G", "https://r2.test/list-lock")
        novel = SqlAlchemyNovelRepository(db).add(Novel(
            id=None, title="Locked", source_key=SK, source_url="https://r2.test/book/lock",
            lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
        ))
        refs = [ChapterRef(index=1, title="l1", url="https://r2.test/l1")]
        ref = NovelRef(title="Locked", url="https://r2.test/book/lock", latest_chapter_title="")
        src = _Src(refs, novels=[ref])
        key = f"crawl-novel:{novel.id}"
        assert try_acquire(key)
        try:
            result = _genre_uc(db, src, tmp_path).execute(genre.id)
        finally:
            release(key)
        assert src.fetched == []
        assert result.synced == 0
        assert any("đang có crawl khác" in m for m in result.messages)
    finally:
        db.close()


# ------------------------------------------------------------ 18. webhook --

def test_webhook_sent_on_novel_crawl_failure(client, monkeypatch):  # noqa: ARG001
    from crawl.api import routers
    from crawl.application import notify
    from crawl.application.dto import CrawlNovelResult

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notify, "send_webhook", lambda url, *, title, body, extra=None: sent.append((title, body)) or True
    )
    db = _db()
    try:
        from platform_.settings_store import set_setting

        set_setting(db, "notify.webhook_url", "https://discord.com/api/webhooks/x")
        routers._notify_novel_failure(db, 999999, CrawlNovelResult.failure(999999, "site chặn"))
        result = CrawlNovelResult(novel_id=999999, chapters_crawled=1, success=True)
        routers._notify_novel_failure(db, 999999, result)
        set_setting(db, "notify.webhook_url", "")
        routers._notify_novel_failure(db, 999999, CrawlNovelResult.failure(999999, "lại lỗi"))
    finally:
        db.close()
    assert len(sent) == 1 and "site chặn" in sent[0][1]


# ------------------------------------------------------ 19. novel progress --

def test_novel_progress_endpoint(client):
    from crawl.application.progress import CrawlProgress
    from platform_.run_progress import publish

    db = _db()
    try:
        novel = SqlAlchemyNovelRepository(db).add(Novel(
            id=None, title="Prog", source_key=SK, source_url="https://r2.test/book/prog",
        ))
    finally:
        db.close()
    assert client.get(f"/api/crawl/novels/{novel.id}/progress").json() == {"progress": None}
    publish(CrawlProgress(task_id=f"novel:{novel.id}", kind="novel", label="x", phase="crawling",
                          chapter_index=3, chapter_total=10))
    data = client.get(f"/api/crawl/novels/{novel.id}/progress").json()["progress"]
    assert data["phase"] == "crawling" and data["chapter_index"] == 3
    assert client.get("/api/crawl/novels/987654321/progress").status_code == 404
