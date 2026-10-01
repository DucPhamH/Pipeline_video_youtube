import io
import time
import zipfile

from ebooklib import epub

from tts.application.export_audio import chapter_metadata


def _wait(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/tts/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    return status


def test_chapter_metadata_marks_ranges():
    text = chapter_metadata([1000, 500], ["Một", "Hai"])
    assert "START=0" in text
    assert "END=1000" in text
    assert "START=1000" in text
    assert "END=1500" in text
    assert "title=Một" in text


def test_zip_export_and_m4b_without_ffmpeg(client, monkeypatch):
    text = "# Một\n\nNội dung chương một đủ để đọc.\n\n# Hai\n\nNội dung chương hai."
    work = client.post(
        "/api/tts/works/import-txt",
        json={"title": "Zip Book", "lang": "vi", "text": text},
    ).json()
    started = client.post(
        f"/api/tts/works/{work['id']}/readings",
        json={"engine": "mock", "preset_id": "nu_ke_cham"},
    )
    job = started.json()["readings"][0]["latest_job"]
    assert _wait(client, job["id"]) == "completed"
    reading_id = started.json()["readings"][0]["id"]
    exported = client.get(f"/api/tts/readings/{reading_id}/export.zip")
    assert exported.status_code == 200
    assert exported.content[:2] == b"PK"
    names = zipfile.ZipFile(io.BytesIO(exported.content)).namelist()
    assert len(names) == 2
    assert names[0].endswith(".mp3")

    monkeypatch.setattr("tts.application.export_audio.ffmpeg_bin", lambda: None)
    m4b = client.get(f"/api/tts/readings/{reading_id}/export.m4b")
    assert m4b.status_code == 503


def test_from_translate_is_idempotent(client):
    payload = {
        "title": "Đã dịch",
        "author": "B",
        "lang": "vi",
        "external_id": "translate:variant:4242",
        "chapters": [
            {"index": 1, "title": "Ch1", "text": "Bản dịch chương một."},
            {"index": 2, "title": "Ch2", "text": "Bản dịch chương hai."},
        ],
    }
    first = client.post("/api/tts/works/from-translate", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    second = client.post("/api/tts/works/from-translate", json=payload)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == first.json()["id"]
    assert len(second.json()["chapters"]) == 2

    updated = client.post(
        "/api/tts/works/from-translate",
        json={
            **payload,
            "chapters": [
                {"index": 1, "title": "Ch1", "text": "Bản mới chương một."},
                {"index": 3, "title": "Ch3", "text": "Chương ba mới."},
            ],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == first.json()["id"]
    assert body["created"] is False
    assert sorted(c["index"] for c in body["chapters"]) == [1, 3]

    from platform_.db import SessionLocal
    from tts.infrastructure.persistence.models import ChapterModel

    db = SessionLocal()
    try:
        rows = db.query(ChapterModel).filter(ChapterModel.work_id == body["id"]).all()
        assert {row.index: row.text for row in rows} == {1: "Bản mới chương một.", 3: "Chương ba mới."}
    finally:
        db.close()


def test_import_epub(client):
    book = epub.EpubBook()
    book.set_identifier("t1")
    book.set_title("EPUB Voice")
    book.set_language("vi")
    book.add_author("C")
    chapter = epub.EpubHtml(title="Ch", file_name="c1.xhtml", lang="vi")
    chapter.content = "<html><body><h1>Mở</h1><p>" + ("nội dung chương. " * 8) + "</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    res = client.post(
        "/api/tts/works/import-epub",
        files={"file": ("book.epub", buf.getvalue(), "application/epub+zip")},
        data={"lang": "vi"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "EPUB Voice"
    assert body["chapters"]
