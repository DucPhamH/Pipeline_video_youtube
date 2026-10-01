"""Import EPUB, xuất EPUB bản dịch, và lượt polish tắt mặc định."""
import io
import time

from ebooklib import epub


def _sample_epub() -> bytes:
    book = epub.EpubBook()
    book.set_identifier("demo")
    book.set_title("EPUB Demo")
    book.set_language("en")
    book.add_author("Writer")
    chapter = epub.EpubHtml(title="One", file_name="chap_1.xhtml", lang="en")
    chapter.content = (
        "<html><body><h1>One</h1>"
        "<p>This is a long enough chapter body for the parser to keep it.</p>"
        "</body></html>"
    )
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def _wait_done(client, job_id: int) -> str:
    deadline = time.time() + 10
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            return status
        time.sleep(0.05)
    return status


def test_import_epub_then_export_translated_epub(client):
    data = _sample_epub()
    r = client.post(
        "/api/translate/works/import-epub",
        files={"file": ("demo.epub", data, "application/epub+zip")},
        data={"lang_src": "en", "lang_tgt": "vi"},
    )
    assert r.status_code == 201, r.text
    work = r.json()
    assert work["title"] == "EPUB Demo"
    assert work["author"] == "Writer"
    assert len(work["chapters"]) >= 1
    variant_id = work["variants"][0]["id"]

    job_id = client.post(f"/api/translate/variants/{variant_id}/jobs").json()["id"]
    assert _wait_done(client, job_id) == "completed"

    exported = client.get(f"/api/translate/variants/{variant_id}/export.epub")
    assert exported.status_code == 200, exported.text
    assert exported.content[:2] == b"PK"

    bilingual = client.get(f"/api/translate/variants/{variant_id}/export.epub?bilingual=true")
    assert bilingual.status_code == 200, bilingual.text
    book = epub.read_epub(io.BytesIO(bilingual.content))
    html = "\n".join(
        item.get_content().decode("utf-8", errors="replace") for item in book.get_items()
    )
    assert 'class="src"' in html
    assert 'class="tgt"' in html
    assert "long enough chapter body" in html


def test_polish_is_off_unless_requested(client):
    r = client.post(
        "/api/translate/works/import-txt",
        json={
            "title": "Polish Demo",
            "lang_src": "en",
            "lang_tgt": "vi",
            "text": "# Chapter One\n\nHello world from the source chapter.",
        },
    )
    assert r.status_code == 201, r.text
    work = r.json()
    plain_id = work["variants"][0]["id"]
    polished = client.post(
        f"/api/translate/works/{work['id']}/variants",
        json={"mode": "full", "mode_params": {"polish": True}},
    )
    assert polished.status_code == 201, polished.text
    assert polished.json()["mode_params"] == {"polish": True}

    plain_job = client.post(f"/api/translate/variants/{plain_id}/jobs").json()["id"]
    polish_job = client.post(
        f"/api/translate/variants/{polished.json()['id']}/jobs"
    ).json()["id"]
    assert _wait_done(client, plain_job) == "completed"
    assert _wait_done(client, polish_job) == "completed"

    plain_txt = client.get(f"/api/translate/variants/{plain_id}/export.txt").text
    polish_txt = client.get(
        f"/api/translate/variants/{polished.json()['id']}/export.txt"
    ).text
    assert "[polished]" not in plain_txt
    assert "[polished]" in polish_txt

    base = client.get(f"/api/translate/works/{work['id']}/estimate?mode=full")
    extra = client.get(f"/api/translate/works/{work['id']}/estimate?mode=full&polish=true")
    assert base.status_code == 200 and extra.status_code == 200
    assert extra.json()["estimated_tokens"] > base.json()["estimated_tokens"]
