import time
import unicodedata
from pathlib import Path

import pytest

from platform_.auth import HEADER, outgoing_headers
from platform_.config import config
from platform_.db import SessionLocal
from tts.application import run_job as run_mod
from tts.application.cast import coverage
from tts.application.pieces import split_roles
from tts.infrastructure.persistence.models import ChapterModel, JobModel, SegmentModel


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/tts/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    return status


def _work(client, external_id: str, texts: list[str]) -> dict:
    res = client.post(
        "/api/tts/works/from-translate",
        json={
            "title": external_id,
            "lang": "vi",
            "external_id": external_id,
            "chapters": [{"index": i + 1, "title": f"Ch{i + 1}", "text": t} for i, t in enumerate(texts)],
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def _finished_reading(client, external_id: str, texts: list[str]) -> dict:
    work = _work(client, external_id, texts)
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nam_ke"})
    reading = started.json()["readings"][0]
    assert _wait(client, reading["latest_job"]["id"]) == "completed"
    return reading


# 1. NFC
def test_coverage_ignores_unicode_normal_form():
    text = "Tiếng Việt có dấu: ngưỡng cửa, đường xa, Ánh trăng."
    nfd = unicodedata.normalize("NFD", text)
    assert coverage(text, nfd) == pytest.approx(1.0)
    assert coverage(nfd, text) == pytest.approx(1.0)


def test_import_stores_nfc_text(client):
    nfd = unicodedata.normalize("NFD", "Chương một: người đàn ông ấy đứng lặng.")
    res = client.post(
        "/api/tts/works/import-txt",
        json={"title": unicodedata.normalize("NFD", "Truyện Việt"), "lang": "vi", "text": nfd},
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == unicodedata.normalize("NFC", "Truyện Việt")
    db = SessionLocal()
    try:
        row = db.query(ChapterModel).filter(ChapterModel.work_id == res.json()["id"]).one()
        assert row.text == unicodedata.normalize("NFC", row.text)
        assert "người" in row.text
    finally:
        db.close()


# 2. generation
def test_stale_run_thread_exits_without_touching_job(client, monkeypatch):
    monkeypatch.setattr("tts.api.routers.launch", lambda _job_id: None)
    work = _work(client, "harden:gen", ["Chương thế hệ."])
    started = client.post(f"/api/tts/works/{work['id']}/readings", json={"engine": "mock", "preset_id": "nam_ke"})
    job_id = started.json()["readings"][0]["latest_job"]["id"]
    old = run_mod._next_generation(job_id)
    new = run_mod._next_generation(job_id)  # bấm đọc tiếp → thread mới
    run_mod.run_job(job_id, generation=old)
    db = SessionLocal()
    try:
        assert db.get(JobModel, job_id).status == "queued"
        assert {s.status for s in db.query(SegmentModel).filter(SegmentModel.job_id == job_id)} == {"pending"}
    finally:
        db.close()
    run_mod.run_job(job_id, generation=new)
    assert client.get(f"/api/tts/jobs/{job_id}").json()["status"] == "completed"


# 3. dash dialogue
def test_dash_without_space_is_dialogue():
    assert split_roles("-Đi thôi!", dialogue=True) == [("dialogue", "Đi thôi!")]
    assert split_roles("-5 độ.", dialogue=True) == [("narrator", "-5 độ.")]


def test_em_dash_tag_in_middle():
    assert split_roles("— A — hắn nói — B.", dialogue=True) == [
        ("dialogue", "A"),
        ("narrator", "hắn nói"),
        ("dialogue", "B."),
    ]


def test_inner_dash_without_speech_tag_stays_dialogue():
    assert split_roles("- Không - không được!", dialogue=True) == [("dialogue", "Không - không được!")]


def test_short_dash_list_is_narration():
    text = "Hắn mang theo:\n- Kiếm\n- Khiên gỗ\n- Bản đồ\nRồi đi."
    assert [role for role, _ in split_roles(text, dialogue=True)] == ["narrator"]
    # Một dòng ngắn đứng riêng vẫn là thoại.
    assert split_roles("- Ừ\nTrời tối.", dialogue=True) == [("dialogue", "Ừ"), ("narrator", "Trời tối.")]


# 4/5. export
def test_export_busy_returns_409(client):
    import tts.application.export_audio as export_audio

    reading = _finished_reading(client, "harden:busy", ["Chương bận."])
    with export_audio._export_slot(reading["id"]):
        assert client.get(f"/api/tts/readings/{reading['id']}/export.zip").status_code == 409
        assert client.get(f"/api/tts/readings/{reading['id']}/export.m4b").status_code == 409
    assert client.get(f"/api/tts/readings/{reading['id']}/export.zip").status_code == 200


def test_m4b_reuses_cached_aac_parts_and_times_from_parts(client, monkeypatch):
    import tts.application.export_audio as export_audio

    reading = _finished_reading(client, "harden:aac", ["Chương AAC một.", "Chương AAC hai."])
    cmds: list[list[str]] = []
    metas: list[str] = []

    class Proc:
        returncode = 0
        stderr = ""
        stdout = "1.0005\n"

    def fake_run(cmd, timeout):
        cmds.append(cmd)
        if Path(cmd[0]).name == "ffprobe":
            assert Path(cmd[-1]).suffix == ".m4a"  # đo part đã transcode, không phải mp3 gốc
            return Proc()
        if "concat" in cmd:
            metas.append(Path(next(c for c in cmd if c.endswith("chapters.txt"))).read_text(encoding="utf-8"))
        Path(cmd[-1]).write_bytes(b"M4B")
        return Proc()

    monkeypatch.setattr(export_audio, "ffmpeg_bin", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(export_audio.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(export_audio, "_run", fake_run)
    assert client.get(f"/api/tts/readings/{reading['id']}/export.m4b").status_code == 200
    assert len([c for c in cmds if "-ar" in c]) == 2
    cmds.clear()
    assert client.get(f"/api/tts/readings/{reading['id']}/export.m4b").status_code == 200
    assert [c for c in cmds if "-ar" in c] == []
    assert "END=2001" in metas[-1]  # 1000.5 + 1000.5, làm tròn trên tổng


def test_chapter_metadata_rounds_cumulative_not_per_chapter():
    from tts.application.export_audio import chapter_metadata

    text = chapter_metadata([333.4] * 3, ["a", "b", "c"])
    assert text.strip().splitlines()[-2] == "END=1000"


def test_clean_exports_removes_leftovers():
    from tts.application.export_audio import clean_exports

    root = config.resolved_audio_dir() / "exports"
    (root / "tmpabc").mkdir(parents=True, exist_ok=True)
    (root / "tmpabc" / "book.m4b").write_bytes(b"x")
    clean_exports()
    assert not any(root.iterdir())


# 6. skipped
def test_job_reports_skipped_segments(client):
    reading = _finished_reading(client, "harden:skip", ["Chương có chữ.", "* * *"])
    job = client.get(f"/api/tts/jobs/{reading['latest_job']['id']}").json()
    assert job["skipped_segments"] == 1
    assert job["done_segments"] == job["total_segments"] == 2


# 7. token
def test_token_auth(client, monkeypatch):
    monkeypatch.setattr(config, "folio_api_token", "s3cret")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/tts/works").status_code == 401
    assert client.get("/api/tts/works", headers={HEADER: "nope"}).status_code == 401
    assert client.get("/api/tts/works", headers={HEADER: "s3cret"}).status_code == 200
    assert client.get("/api/tts/works", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/tts/works?token=s3cret").status_code == 200
    body = {"title": "t", "text": "x"}
    assert client.post("/api/tts/works/import-txt?token=s3cret", json=body).status_code == 401
    assert outgoing_headers() == {HEADER: "s3cret"}
    monkeypatch.setattr(config, "folio_api_token", "")
    assert outgoing_headers() == {}
    assert client.get("/api/tts/works").status_code == 200


def test_cors_preflight_allows_token_header(client, monkeypatch):
    monkeypatch.setattr(config, "folio_api_token", "s3cret")
    res = client.options(
        "/api/tts/works",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": HEADER,
        },
    )
    assert res.status_code == 200
    assert HEADER.lower() in res.headers["access-control-allow-headers"].lower()


# 8. upload limit
def test_upload_limit(client, monkeypatch):
    monkeypatch.setattr(config, "tts_max_upload_mb", 1)
    big = "a" * (1024 * 1024 + 10)
    assert client.post("/api/tts/works/import-txt", json={"title": "big", "text": big}).status_code == 413
    res = client.post(
        "/api/tts/works/import-epub",
        files={"file": ("big.epub", b"x" * (2 * 1024 * 1024), "application/epub+zip")},
    )
    assert res.status_code == 413
