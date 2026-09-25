"""Bug thật user gặp: job full ĐẦU TIÊN của 1 Work (glossary rỗng) chạy suốt mà
không có glossary nào áp dụng — dịch xong mới trích (quá muộn), nên 2 model
trong pool đặt tên nhân vật khác nhau ngay từ chương đầu. Giờ glossary được
trích TRƯỚC khi dịch bất kỳ chương nào — verify: MỌI segment (dù slot/model
nào xử lý) đều thấy glossary đã có sẵn trong prompt, kể cả segment đầu tiên.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class _SeedAwareHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        system_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "system"), "")

        if "preparing a translation glossary BEFORE translating" in system_msg:
            reply = json.dumps([{"source_term": "Ryu", "target_term": "Long"}])
        else:
            reply = "[GLOSSARY-OK]" if "Ryu → Long" in system_msg else "[NO-GLOSSARY]"

        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start():
    server = HTTPServer(("127.0.0.1", 0), _SeedAwareHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _add_ai(client, label, port):
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": label,
            "kind": "local",
            "base_url": f"http://127.0.0.1:{port}/v1",
            "model": "m",
            "api_key": "",
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait_job(client, job_id: int, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def test_glossary_seeded_before_first_segment_translates_in_pool_job(client):
    server, port = _start()
    try:
        ai_a = _add_ai(client, "Seed Pool A", port)
        ai_b = _add_ai(client, "Seed Pool B", port)

        text = "\n\n".join(f"# Ch{i}\n\nRyu appears.\n" for i in range(1, 5))  # 4 chương
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Seed Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
        )
        assert r.status_code == 201, r.text
        work_id = r.json()["id"]
        variant_id = r.json()["variants"][0]["id"]

        assert client.get(f"/api/translate/works/{work_id}/glossary").json() == []

        r = client.post(
            f"/api/translate/variants/{variant_id}/jobs",
            json={"ai_provider_ids": [ai_a, ai_b], "ai_mode": "pool"},
        )
        assert r.status_code == 202, r.text
        job = _wait_job(client, r.json()["id"])
        assert job["status"] == "completed", job

        glossary = client.get(f"/api/translate/works/{work_id}/glossary").json()
        assert any(g["source_term"] == "Ryu" and g["target_term"] == "Long" for g in glossary), glossary

        segs = client.get(f"/api/translate/jobs/{job['id']}/segments").json()
        assert len(segs) == 4
        for s in segs:
            detail = client.get(f"/api/translate/segments/{s['id']}").json()
            # KỂ CẢ chương 1 (segment đầu tiên xử lý) cũng đã thấy glossary —
            # chứng minh glossary được trích TRƯỚC, không phải sau khi dịch xong.
            assert detail["output_text"] == "[GLOSSARY-OK]", (s["chapter_index"], detail)
    finally:
        server.shutdown()
        server.server_close()
