"""Bảo mật (đổi host giữ key, giới hạn upload, làm sạch lỗi, token dùng chung)
và QA output (cờ segment, refusal → lỗi không cache, dịch lại segment bị gắn cờ)."""
import io
import json
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest


def _wait(client, job_id: int, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


# --- 9. đổi base_url sang host khác phải nhập lại key


def test_changing_base_url_host_requires_new_key(client):
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": "Sec", "kind": "openai", "base_url": "https://api.openai.com/v1",
              "model": "gpt", "api_key": "sk-secret-original"},
    )
    pid = r.json()["id"]
    url = f"/api/translate/ai-providers/{pid}"
    r = client.put(url, json={"base_url": "https://evil.example.com/v1"})
    assert r.status_code == 422, r.text
    # Cùng host, khác path → được giữ key.
    r = client.put(url, json={"base_url": "https://api.openai.com/v2"})
    assert r.status_code == 200 and r.json()["has_api_key"]
    r = client.put(url, json={"base_url": "https://other.example.com/v1", "api_key": "sk-new-key-1234"})
    assert r.status_code == 200, r.text
    assert r.json()["api_key_hint"] == "…1234" and r.json()["key_count"] == 1


# --- 10. giới hạn upload


def test_import_limits(client, monkeypatch):
    from platform_.config import config

    monkeypatch.setattr(config, "translate_max_upload_mb", 1)
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Big", "lang_src": "en", "text": "a" * (1024 * 1024 + 10)},
    )
    assert r.status_code == 413
    r = client.post(
        "/api/translate/works/import-epub",
        files={"file": ("big.epub", b"x" * (1024 * 1024 + 10), "application/epub+zip")},
    )
    assert r.status_code == 413
    r = client.post(
        "/api/translate/works/import-epub",
        files={"file": ("bad.epub", b"not a zip", "application/epub+zip")},
    )
    assert r.status_code == 400

    monkeypatch.setattr(config, "translate_max_epub_uncompressed_mb", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/bomb.xhtml", b"\0" * (3 * 1024 * 1024))
    r = client.post(
        "/api/translate/works/import-epub",
        files={"file": ("bomb.epub", buf.getvalue(), "application/epub+zip")},
    )
    assert r.status_code == 413, r.text


# --- 11. lỗi đã làm sạch + mã ngắn


def test_format_error_strips_secrets_and_adds_code():
    from translate.application.error_codes import format_error

    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/chat?key=AIzaSyA1234567890abcdefghijk")
    resp = httpx.Response(401, request=req)
    exc = httpx.HTTPStatusError(
        "401 from https://generativelanguage.googleapis.com/v1/chat?key=AIzaSyA1234567890abcdefghijk: "
        '{"error": "Incorrect API key provided: sk-proj-abcdefghijklmnop", "api_key": "raw-secret"}',
        request=req,
        response=resp,
    )
    msg = format_error(exc)
    assert msg.startswith("[auth] ")
    assert "AIza" not in msg and "sk-proj" not in msg and "raw-secret" not in msg and "?key" not in msg
    assert format_error(RuntimeError("429 Too Many Requests")).startswith("[rate_limited]")
    assert format_error(RuntimeError("Output bị cắt cụt (finish_reason=length)")).startswith("[truncated]")
    assert format_error(httpx.ConnectError("boom")).startswith("[network]")
    assert format_error(RuntimeError("x" * 2000)).__len__() < 400


# --- 12. token dùng chung


def test_shared_token_auth(client, monkeypatch):
    from platform_.auth import outgoing_headers
    from platform_.config import config

    monkeypatch.setattr(config, "folio_api_token", "s3cret")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/translate/health").status_code == 200
    assert client.get("/api/translate/works").status_code == 401
    assert client.get("/api/translate/works", headers={"X-Folio-Token": "wrong"}).status_code == 401
    assert client.get("/api/translate/works", headers={"X-Folio-Token": "s3cret"}).status_code == 200
    assert client.get("/api/translate/works", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/translate/works?token=s3cret").status_code == 200
    assert client.post("/api/translate/ai-providers?token=s3cret", json={}).status_code == 401
    pre = client.options(
        "/api/translate/works",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-folio-token",
        },
    )
    assert pre.status_code == 200
    assert "x-folio-token" in pre.headers.get("access-control-allow-headers", "").lower()
    assert outgoing_headers() == {"X-Folio-Token": "s3cret"}
    monkeypatch.setattr(config, "folio_api_token", "")
    assert client.get("/api/translate/works").status_code == 200
    assert outgoing_headers() == {}


# --- 13. QA output


def test_check_output_rules():
    from translate.application.segment_qa import check_output

    src = "第一章 " + "他走进了房间，看着窗外的雨。" * 30
    assert check_output(source=src, output="Tôi không thể dịch nội dung này.", lang_src="zh", lang_tgt="vi") == [
        "refusal",
        "length_ratio",
    ]
    assert "refusal" in check_output(source=src, output="As an AI language model, I won't.", lang_src="zh", lang_tgt="en")
    leftover = "Anh bước vào phòng " + "他走进了房间，看着窗外的雨。" * 20
    assert "untranslated" in check_output(source=src, output=leftover, lang_src="zh", lang_tgt="vi")
    loop = "\n".join(["Anh ấy nhìn ra cửa sổ và thấy mưa."] * 8)
    assert "repetition" in check_output(source=src, output=loop, lang_src="zh", lang_tgt="vi")
    good = "\n".join(f"Đoạn {i}: anh bước vào phòng, nhìn mưa ngoài cửa sổ rất lâu." for i in range(20))
    assert check_output(source=src, output=good, lang_src="zh", lang_tgt="vi") == []
    # Lời thoại "I can't" bình thường trong bản dịch dài không bị coi là từ chối.
    dialogue = "I can't believe it, he said. " * 40
    assert "refusal" not in check_output(source=src, output=dialogue, lang_src="zh", lang_tgt="en")


class _QaHandler(BaseHTTPRequestHandler):
    mode = {"value": "bad"}

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        user = next((m["content"] for m in payload["messages"] if m["role"] == "user"), "")
        if "REFUSE" in user:
            reply = "I'm sorry, but I can't help with that request."
        elif "LEFTOVER" in user and self.mode["value"] == "bad":
            reply = "Anh ấy " + "他走进了房间看着窗外的雨" * 10
        else:
            reply = "Bản dịch tốt cho chương này, nội dung đầy đủ và trôi chảy."
        raw = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def qa_ai(client, monkeypatch):
    from translate.application import run_job as rj

    monkeypatch.setattr(rj, "MIN_CALL_INTERVAL", 0.0)
    _QaHandler.mode["value"] = "bad"
    server = HTTPServer(("127.0.0.1", 0), _QaHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    r = client.post(
        "/api/translate/ai-providers",
        json={"label": f"QA {uuid.uuid4().hex[:4]}", "kind": "local",
              "base_url": f"http://127.0.0.1:{server.server_address[1]}/v1",
              "model": "qa-model", "api_key": "", "requires_api_key": False},
    )
    yield r.json()["id"]
    server.shutdown()


def test_qa_flags_refusal_failure_and_retranslate_flagged(client, qa_ai):
    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.repositories import SegmentRepository, TranslationCacheRepository

    tag = uuid.uuid4().hex[:6]
    text = (
        f"# Ch1\n\n{tag} LEFTOVER 第一章内容。\n\n"
        f"# Ch2\n\n{tag} REFUSE 第二章内容。\n\n"
        f"# Ch3\n\n{tag} 第三章内容。"
    )
    work = client.post(
        "/api/translate/works/import-txt",
        json={"title": f"QA {tag}", "lang_src": "zh", "lang_tgt": "vi", "text": text},
    ).json()
    job = client.post(
        f"/api/translate/variants/{work['variants'][0]['id']}/jobs", json={"ai_provider_id": qa_ai}
    ).json()
    got = _wait(client, job["id"])
    assert got["status"] == "completed" and got["failed_segments"] == 1, got
    assert got["flagged_segments"] == 2  # untranslated (DONE) + refusal (FAILED)
    segs = {s["chapter_index"]: s for s in client.get(f"/api/translate/jobs/{job['id']}/segments").json()}
    assert segs[1]["status"] == "done" and segs[1]["qa_flags"] == ["untranslated"]
    assert segs[2]["status"] == "failed" and segs[2]["error"].startswith("[refusal]")
    assert segs[3]["qa_flags"] == []
    detail = client.get(f"/api/translate/segments/{segs[1]['id']}").json()
    assert detail["qa_flags"] == ["untranslated"]

    db = SessionLocal()
    try:
        refused = SegmentRepository(db).get(segs[2]["id"])
        assert TranslationCacheRepository(db).get(refused.cache_key) is None  # refusal không cache
    finally:
        db.close()

    assert client.post(f"/api/translate/jobs/{job['id']}/retranslate-flagged?flag=bogus").status_code == 400
    _QaHandler.mode["value"] = "good"
    r = client.post(f"/api/translate/jobs/{job['id']}/retranslate-flagged?flag=untranslated")
    assert r.status_code == 202, r.text
    got = _wait(client, job["id"])
    segs = {s["chapter_index"]: s for s in client.get(f"/api/translate/jobs/{job['id']}/segments").json()}
    assert segs[1]["status"] == "done" and segs[1]["qa_flags"] == []
    out = client.get(f"/api/translate/segments/{segs[1]['id']}").json()["output_text"]
    assert out.startswith("Bản dịch tốt")
