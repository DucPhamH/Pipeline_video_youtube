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


def test_sites_due_only_matching_time_and_enabled():
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
    assert due == [("a", "hot")]


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
