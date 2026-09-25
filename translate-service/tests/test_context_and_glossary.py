"""2 tính năng "tự động, không cần sửa tay":
1. Rolling context — pov/audio_cut đưa đuôi chương adapt trước vào prompt chương
   sau, giữ mạch truyện dù mỗi chương là 1 lệnh gọi LLM độc lập.
2. Auto-glossary — sau khi variant full dịch xong (Work chưa có glossary nào),
   tự trích tên nhân vật/địa danh từ vài chương đầu, không bắt user gõ tay.
Dùng HTTP server thật (không mock) để nhìn đúng nội dung prompt server nhận được.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class _FakeAiHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        system_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "system"), "")
        user_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")

        if "compiling a translation glossary" in system_msg:
            reply = json.dumps([{"source_term": "Ryu", "target_term": "Long"}])
        else:
            marker = "[CTX-SEEN] " if "STORY CONTEXT" in system_msg else ""
            reply = f"{marker}{user_msg}"

        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start():
    server = HTTPServer(("127.0.0.1", 0), _FakeAiHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _wait_job(client, job_id: int, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def test_rolling_context_and_auto_glossary(client):
    server, port = _start()
    try:
        r = client.post(
            "/api/translate/ai-providers",
            json={
                "label": "Ctx Fake AI",
                "kind": "local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "m",
                "api_key": "",
                "requires_api_key": False,
            },
        )
        ai_id = r.json()["id"]

        text = "# Ch1\n\nRyu walks in.\n\n# Ch2\n\nRyu walks out.\n"
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "Ctx Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
        )
        assert r.status_code == 201, r.text
        work_id = r.json()["id"]
        full_variant_id = r.json()["variants"][0]["id"]

        # ---- auto-glossary: Work chưa có glossary nào trước khi full chạy ----
        assert client.get(f"/api/translate/works/{work_id}/glossary").json() == []

        r = client.post(f"/api/translate/variants/{full_variant_id}/jobs", json={"ai_provider_id": ai_id})
        assert r.status_code == 202, r.text
        full_job = _wait_job(client, r.json()["id"])
        assert full_job["status"] == "completed", full_job

        # auto-extract chạy TRONG cùng thread nền, NGAY SAU khi job chuyển
        # completed — job "completed" không đảm bảo extraction đã xong, poll thêm.
        deadline = time.time() + 10
        glossary: list = []
        while time.time() < deadline:
            glossary = client.get(f"/api/translate/works/{work_id}/glossary").json()
            if glossary:
                break
            time.sleep(0.1)
        assert any(g["source_term"] == "Ryu" and g["target_term"] == "Long" for g in glossary), glossary
        assert all(g["notes"] == "Tự động trích xuất" for g in glossary if g["source_term"] == "Ryu")

        # ---- rolling context: fork pov từ full, chương 2 phải "thấy" đuôi chương 1 ----
        r = client.post(
            f"/api/translate/works/{work_id}/variants",
            json={"mode": "pov", "mode_params": {"target_pov": "third_person"}},
        )
        assert r.status_code == 201, r.text
        pov_variant_id = r.json()["id"]

        r = client.post(f"/api/translate/variants/{pov_variant_id}/jobs", json={"ai_provider_id": ai_id})
        assert r.status_code == 202, r.text
        pov_job = _wait_job(client, r.json()["id"])
        assert pov_job["status"] == "completed", pov_job

        segs = client.get(f"/api/translate/jobs/{pov_job['id']}/segments").json()
        by_chapter = {s["chapter_index"]: s for s in segs}
        detail1 = client.get(f"/api/translate/segments/{by_chapter[1]['id']}").json()
        detail2 = client.get(f"/api/translate/segments/{by_chapter[2]['id']}").json()
        assert "[CTX-SEEN]" not in detail1["output_text"]  # chương đầu — chưa có chương trước
        assert "[CTX-SEEN]" in detail2["output_text"]  # chương sau — thấy đuôi chương 1
    finally:
        server.shutdown()
        server.server_close()
