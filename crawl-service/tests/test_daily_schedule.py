"""Lịch quét hàng ngày theo setting riêng từng site — opt-in."""
from __future__ import annotations

import datetime as dt

from platform_.scheduler import sites_due_now


def _cfg(
    *,
    enabled: dict[str, bool] | None = None,
    hour: dict[str, int] | None = None,
    minute: dict[str, int] | None = None,
    genre: dict[str, str] | None = None,
):
    enabled = enabled or {}
    hour = hour or {}
    minute = minute or {}
    genre = genre or {}
    return dict(
        get_enabled=lambda sk: enabled.get(sk, False),
        get_hour=lambda sk: hour.get(sk, 6),
        get_minute=lambda sk: minute.get(sk, 0),
        get_genre_key=lambda sk: genre.get(sk, ""),
    )


def test_sites_due_empty_when_nothing_enabled():
    due = sites_due_now(
        now=dt.datetime(2026, 9, 18, 6, 0),
        source_keys=["a", "b"],
        already_fired=set(),
        **_cfg(hour={"a": 6, "b": 6}, genre={"a": "x", "b": "y"}),
    )
    assert due == []


def test_sites_due_when_time_reached_and_enabled():
    """Đến hạn khi now >= giờ hẹn hôm nay (không đòi khớp đúng phút) —
    c (7:00) bị tick trễ lúc 7:30 vẫn chạy; b (8:30) chưa tới giờ."""
    due = sites_due_now(
        now=dt.datetime(2026, 9, 18, 7, 30),
        source_keys=["a", "b", "c"],
        already_fired=set(),
        **_cfg(
            enabled={"a": True, "b": True, "c": True},
            hour={"a": 7, "b": 8, "c": 7},
            minute={"a": 30, "b": 30, "c": 0},
            genre={"a": "hot", "b": "hot", "c": "hot"},
        ),
    )
    assert due == [("a", "hot"), ("c", "hot")]


def test_sites_due_skips_when_persisted_last_fired_is_today():
    due = sites_due_now(
        now=dt.datetime(2026, 9, 18, 9, 0),
        source_keys=["a", "b"],
        already_fired=set(),
        get_last_fired=lambda sk: {"a": "2026-09-18", "b": "2026-09-17"}[sk],
        **_cfg(enabled={"a": True, "b": True}, genre={"a": "hot", "b": "hot"}),
    )
    assert due == [("b", "hot")]


def test_tick_dispatches_in_background_without_persisting_last_fired(client, monkeypatch):  # noqa: ARG001
    """Tick chỉ đánh dấu in-process; last_fired trong DB ghi khi crawl THẬT SỰ
    bắt đầu (trong _run_due_sites, sau khi lấy được khoá)."""
    import threading

    from platform_ import scheduler
    from platform_.db import SessionLocal
    from platform_.settings_store import get_setting, per_site_key, set_setting

    started = threading.Event()
    release = threading.Event()
    calls: list[list[tuple[str, str]]] = []

    def fake_run(due, today=None):
        calls.append(due)
        started.set()
        release.wait(5)

    monkeypatch.setattr(scheduler, "_run_due_sites", fake_run)
    monkeypatch.setattr(scheduler, "scheduler_now", lambda: dt.datetime(2026, 9, 18, 23, 0))
    monkeypatch.setattr(scheduler, "_fired_dates", set())
    sk = "bqgxs_com"
    db = SessionLocal()
    try:
        set_setting(db, per_site_key("daily_enabled", sk), True)
        set_setting(db, per_site_key("daily_genre_key", sk), "xuanhuan")
        set_setting(db, scheduler.last_fired_key(sk), "")
    finally:
        db.close()
    try:
        threads = scheduler.run_daily_crawl_tick()
        assert started.wait(5)
        assert threads and threads[0].is_alive()  # tick đã trả về, crawl vẫn đang chạy nền
        assert (sk, "xuanhuan") in calls[0]
        db = SessionLocal()
        try:
            assert get_setting(db, scheduler.last_fired_key(sk)) == ""
        finally:
            db.close()
        # Tick sau cùng ngày (cùng process) không dispatch lại
        assert scheduler.run_daily_crawl_tick() == []
    finally:
        release.set()
        db = SessionLocal()
        try:
            set_setting(db, per_site_key("daily_enabled", sk), False)
            set_setting(db, per_site_key("daily_genre_key", sk), "")
        finally:
            db.close()


def _daily_genre(db, sk: str):
    from crawl.infrastructure.persistence.repositories import SqlAlchemyGenreRepository

    return SqlAlchemyGenreRepository(db).get_or_create(sk, "daily_lf_test", "Daily LF", "https://x/list")


def test_run_due_sites_marks_last_fired_only_when_crawl_starts(client, monkeypatch):  # noqa: ARG001
    from crawl.application.dto import CrawlGenreResult
    from platform_ import scheduler
    from platform_.db import SessionLocal
    from platform_.locks import release, try_acquire
    from platform_.settings_store import get_setting, set_setting

    sk = "bgq99_cc"
    db = SessionLocal()
    try:
        genre = _daily_genre(db, sk)
        set_setting(db, scheduler.last_fired_key(sk), "")
    finally:
        db.close()
    ran: list[int] = []

    def fake_execute(self, genre_id):
        ran.append(genre_id)
        return CrawlGenreResult(genre_id=genre_id)

    monkeypatch.setattr(scheduler.CrawlGenreUseCase, "execute", fake_execute)
    monkeypatch.setattr(scheduler, "_fired_dates", {(sk, "2026-09-18")})

    # Đang có lượt khác giữ khoá -> không chạy, KHÔNG ghi last_fired, bỏ dấu in-process.
    lock = f"genre-run:{genre.id}"
    assert try_acquire(lock)
    try:
        scheduler._run_due_sites([(sk, "daily_lf_test")], today="2026-09-18")
    finally:
        release(lock)
    db = SessionLocal()
    try:
        assert get_setting(db, scheduler.last_fired_key(sk)) == ""
    finally:
        db.close()
    assert ran == []
    assert (sk, "2026-09-18") not in scheduler._fired_dates

    scheduler._run_due_sites([(sk, "daily_lf_test")], today="2026-09-18")
    assert ran == [genre.id]
    db = SessionLocal()
    try:
        assert get_setting(db, scheduler.last_fired_key(sk)) == "2026-09-18"
    finally:
        db.close()


def test_seed_last_fired_when_schedule_enabled_after_hour(client):  # noqa: ARG001
    from platform_ import scheduler
    from platform_.db import SessionLocal
    from platform_.settings_store import get_setting, per_site_key, set_setting

    sk = "fsshu_com"
    db = SessionLocal()
    try:
        set_setting(db, per_site_key("daily_enabled", sk), True)
        set_setting(db, per_site_key("daily_hour", sk), 6)
        set_setting(db, per_site_key("daily_minute", sk), 0)
        # Trước giờ hẹn -> không seed (vẫn chạy hôm nay đúng giờ)
        assert scheduler.seed_last_fired_if_past(db, sk, now=dt.datetime(2026, 9, 18, 5, 0)) is False
        # Sau giờ hẹn -> seed hôm nay, không quét ngay
        assert scheduler.seed_last_fired_if_past(db, sk, now=dt.datetime(2026, 9, 18, 9, 0)) is True
        assert get_setting(db, scheduler.last_fired_key(sk)) == "2026-09-18"
        # Startup chỉ seed site CHƯA có key nào
        assert sk not in scheduler.seed_last_fired_on_startup(db, now=dt.datetime(2026, 9, 19, 9, 0))
    finally:
        set_setting(db, per_site_key("daily_enabled", sk), False)
        db.close()


def test_settings_hide_last_fired_keys(client):
    from platform_ import scheduler
    from platform_.db import SessionLocal
    from platform_.settings_store import set_setting

    db = SessionLocal()
    try:
        set_setting(db, scheduler.last_fired_key("bqgxs_com"), "2026-09-18")
    finally:
        db.close()
    values = client.get("/api/crawl/settings").json()["values"]
    assert not any(k.startswith("scheduler.daily_last_fired.") for k in values)
    r = client.patch("/api/crawl/settings", json={"values": {scheduler.last_fired_key("bqgxs_com"): "x"}})
    assert r.status_code == 422


def test_sites_due_skips_missing_genre_key():
    due = sites_due_now(
        now=dt.datetime(2026, 9, 18, 6, 0),
        source_keys=["a"],
        already_fired=set(),
        **_cfg(enabled={"a": True}, hour={"a": 6}, minute={"a": 0}, genre={"a": ""}),
    )
    assert due == []


def test_sites_due_skips_already_fired_today():
    due = sites_due_now(
        now=dt.datetime(2026, 9, 18, 6, 0),
        source_keys=["a"],
        already_fired={("a", "2026-09-18")},
        **_cfg(enabled={"a": True}, hour={"a": 6}, minute={"a": 0}, genre={"a": "hot"}),
    )
    assert due == []


def test_daily_settings_seeded_off_by_default(client):
    values = client.get("/api/crawl/settings").json()["values"]
    assert values["crawl.daily_enabled.bqgxs_com"] is False
    assert values["crawl.daily_genre_key.bqgxs_com"] == ""
    assert values["crawl.daily_hour.bqgxs_com"] == 6
    assert values["crawl.daily_minute.bqgxs_com"] == 0

    client.patch(
        "/api/crawl/settings",
        json={
            "values": {
                "crawl.daily_enabled.bqgxs_com": True,
                "crawl.daily_hour.bqgxs_com": 9,
                "crawl.daily_minute.bqgxs_com": 15,
                "crawl.daily_genre_key.bqgxs_com": "xuanhuan",
            }
        },
    )
    after = client.get("/api/crawl/settings").json()["values"]
    assert after["crawl.daily_enabled.bqgxs_com"] is True
    assert after["crawl.daily_hour.bqgxs_com"] == 9
    assert after["crawl.daily_minute.bqgxs_com"] == 15
    assert after["crawl.daily_genre_key.bqgxs_com"] == "xuanhuan"
    # Site khác không bị đụng
    assert after["crawl.daily_enabled.bgq99_cc"] is False
