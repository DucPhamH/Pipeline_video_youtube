"""track_story_state (mode_params) — tóm tắt trạng thái truyện LŨY KẾ chạy dọc
sách, khác rolling context (chỉ đuôi chương ngay trước). Dùng HTTP server thật
để xác nhận state của chương N-1 thực sự được đưa vào prompt của chương N."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class _StateAwareHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        system_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "system"), "")
        user_msg = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")

        if "maintain a running STORY STATE summary" in system_msg:
            # lệnh gọi phụ summarize_state() — trả state mới, khác state cũ để
            # phân biệt được state đã "lớn dần" qua từng chương.
            reply = f"- state-after:{user_msg[:60]}"
        else:
            marker = "[STATE-SEEN] " if "STORY STATE SO FAR" in system_msg else ""
            reply = f"{marker}{user_msg}"

        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start():
    server = HTTPServer(("127.0.0.1", 0), _StateAwareHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _wait_job(client, job_id: int, timeout: float = 45) -> dict:  # summarize cũng qua giãn cách
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/translate/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def test_story_state_carries_across_chapters_single_ai(client):
    server, port = _start()
    try:
        r = client.post(
            "/api/translate/ai-providers",
            json={
                "label": "State AI",
                "kind": "local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "m",
                "api_key": "",
                "requires_api_key": False,
            },
        )
        ai_id = r.json()["id"]

        text = "# Ch1\n\nBody1.\n\n# Ch2\n\nBody2.\n\n# Ch3\n\nBody3.\n"
        r = client.post(
            "/api/translate/works/import-txt",
            json={"title": "State Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
        )
        assert r.status_code == 201, r.text
        work_id = r.json()["id"]

        # Variant full RIÊNG có bật track_story_state (variant mặc định lúc
        # import không có cờ này).
        r = client.post(
            f"/api/translate/works/{work_id}/variants",
            json={"mode": "full", "mode_params": {"track_story_state": True}},
        )
        assert r.status_code == 201, r.text
        variant_id = r.json()["id"]
        assert r.json()["mode_params"] == {"track_story_state": True}

        r = client.post(f"/api/translate/variants/{variant_id}/jobs", json={"ai_provider_id": ai_id})
        assert r.status_code == 202, r.text
        job = _wait_job(client, r.json()["id"])
        assert job["status"] == "completed", job

        segs = client.get(f"/api/translate/jobs/{job['id']}/segments").json()
        by_chapter = {s["chapter_index"]: s for s in segs}
        detail1 = client.get(f"/api/translate/segments/{by_chapter[1]['id']}").json()
        detail2 = client.get(f"/api/translate/segments/{by_chapter[2]['id']}").json()
        detail3 = client.get(f"/api/translate/segments/{by_chapter[3]['id']}").json()

        assert "[STATE-SEEN]" not in detail1["output_text"]  # chương đầu chưa có state
        assert "[STATE-SEEN]" in detail2["output_text"]  # thấy state của chương 1
        assert "[STATE-SEEN]" in detail3["output_text"]  # thấy state của chương 2
    finally:
        server.shutdown()
        server.server_close()


def test_track_story_state_off_by_default_and_survives_full_mode_normalize(client):
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Default Off Demo", "lang_src": "en", "lang_tgt": "vi", "text": "# Ch1\n\nBody.\n"},
    )
    work_id = r.json()["id"]
    assert r.json()["variants"][0]["mode_params"] == {}  # mặc định không có cờ

    r = client.post(f"/api/translate/works/{work_id}/variants", json={"mode": "full"})
    assert r.json()["mode_params"] == {}

    r = client.post(
        f"/api/translate/works/{work_id}/variants",
        json={"mode": "full", "mode_params": {"track_story_state": True}},
    )
    assert r.json()["mode_params"] == {"track_story_state": True}
