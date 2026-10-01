"""Bảng duyệt tên: duyệt tên 1 lần rồi áp lại lên chương đã dịch (không dịch lại)."""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from translate.application.name_apply import build_pattern, replace_names

API = "/api/translate"


# --- Engine thay thế ------------------------------------------------------------


def test_replace_single_pass_no_chaining():
    out, counts = replace_names("A gặp B. A và B.", {"A": "B", "B": "C"})
    assert out == "B gặp C. B và C."
    assert counts == {"A": 2, "B": 2}


def test_replace_longest_first():
    out, _ = replace_names("Lan Anh và Lan", {"Lan": "Mai", "Lan Anh": "Hồng Nhung"})
    assert out == "Hồng Nhung và Mai"


def test_replace_unicode_word_boundaries_vietnamese():
    text = "Lan đi. Lành mạnh, Lanh lợi, (Lan) và Lan, cả Thuỳ Lan."
    out, counts = replace_names(text, {"Lan": "Mai"})
    assert out == "Mai đi. Lành mạnh, Lanh lợi, (Mai) và Mai, cả Thuỳ Mai."
    assert counts == {"Lan": 4}
    # Tên có dấu ở cuối không khớp nửa chừng chữ dài hơn.
    out, _ = replace_names("Hà Nội, Hà Nộii", {"Hà Nội": "Sài Gòn"})
    assert out == "Sài Gòn, Hà Nộii"


def test_replace_exact_case_and_regex_chars():
    out, _ = replace_names("lan và Lan", {"Lan": "Mai"})
    assert out == "lan và Mai"
    out, _ = replace_names("Gặp Mr. X (a.k.a) ở đây", {"Mr. X": "Ông Y", "a.k.a": "tức"})
    assert out == "Gặp Ông Y (tức) ở đây"
    assert build_pattern([]) is None


# --- API -------------------------------------------------------------------------


def _wait_job(client, job_id: int, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"{API}/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def _import(client, title: str, chapters: list[str]) -> dict:
    text = "\n\n".join(f"# Ch{i}\n\n{body}\n" for i, body in enumerate(chapters, 1))
    r = client.post(
        f"{API}/works/import-txt",
        json={"title": title, "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _add_term(client, work_id, src, tgt, **extra):
    r = client.post(
        f"{API}/works/{work_id}/glossary", json={"source_term": src, "target_term": tgt, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _translate_full(client, work) -> int:
    variant_id = work["variants"][0]["id"]
    r = client.post(f"{API}/variants/{variant_id}/jobs", json={})
    assert r.status_code == 202, r.text
    job = _wait_job(client, r.json()["id"])
    assert job["status"] == "completed", job
    return job["id"]


def _outputs(client, job_id) -> dict[int, str]:
    out = {}
    for s in client.get(f"{API}/jobs/{job_id}/segments").json():
        out[s["chapter_index"]] = client.get(f"{API}/segments/{s['id']}").json()["output_text"]
    return out


def test_glossary_kind_status_and_candidates_excluded_from_prompt(client):
    work = _import(client, "Names Prompt", ["Alice meets Bob.", "Bob waves."])
    wid = work["id"]
    t = _add_term(client, wid, "Alice", "Lan", protected=True, kind="character")
    assert t["kind"] == "character" and t["status"] == "approved"
    cand = _add_term(client, wid, "Bob", "Bốp", protected=True, status="candidate")
    assert cand["status"] == "candidate"
    assert client.post(
        f"{API}/works/{wid}/glossary", json={"source_term": "X", "kind": "weird"}
    ).status_code == 400

    # PUT không gửi kind/status → giữ nguyên.
    r = client.put(
        f"{API}/works/{wid}/glossary/{t['id']}",
        json={"source_term": "Alice", "target_term": "Lan", "protected": True},
    )
    assert r.json()["kind"] == "character" and r.json()["status"] == "approved"

    job_id = _translate_full(client, work)
    outs = _outputs(client, job_id)
    # Mock thay thuật ngữ protected ĐÃ DUYỆT; candidate không vào prompt.
    assert "Lan meets Bob" in outs[1]
    assert "Bốp" not in outs[1] + outs[2]


def test_names_list_apply_dry_run_apply_undo_and_export(client):
    work = _import(
        client,
        "Names Apply",
        ["Alice went to Hanoi. Alice smiled.", "Lành said hi to Alice.", "Nobody here."],
    )
    wid = work["id"]
    full_id = work["variants"][0]["id"]
    alice = _add_term(client, wid, "Alice", "Lan", protected=True, kind="character")
    hanoi = _add_term(client, wid, "Hanoi", "Hà Nội", protected=True, kind="place")
    empty = _add_term(client, wid, "Ghost", "")
    job_id = _translate_full(client, work)
    before = _outputs(client, job_id)
    assert "Lan went to Hà Nội" in before[1]

    names = {n["source_term"]: n for n in client.get(f"{API}/works/{wid}/names").json()}
    assert names["Alice"]["source_chapter_count"] == 2
    assert names["Hanoi"]["source_chapter_count"] == 1
    assert names["Alice"]["output_hits"] == [{"variant_id": full_id, "mode": "full", "segments": 2}]
    assert names["Ghost"]["output_hits"] == []
    assert names["Alice"]["kind"] == "character" and names["Alice"]["status"] == "approved"

    # Tên mới rỗng → 422.
    r = client.post(
        f"{API}/works/{wid}/names/apply",
        json={"changes": [{"term_id": alice["id"], "new_target": "  "}], "dry_run": True},
    )
    assert r.status_code == 422, r.text

    changes = [
        {"term_id": alice["id"], "new_target": "Hà Nội"},  # A→B và B→C: không nối chuỗi
        {"term_id": hanoi["id"], "new_target": "Sài Gòn"},
        {"term_id": empty["id"], "new_target": "Ma"},
    ]
    r = client.post(f"{API}/works/{wid}/names/apply", json={"changes": changes, "dry_run": True})
    assert r.status_code == 200, r.text
    dry = r.json()
    assert dry["batch_id"] is None
    assert dry["total_replacements"] == 4
    per = {p["term_id"]: p for p in dry["per_term"]}
    assert per[alice["id"]] == {
        "term_id": alice["id"],
        "old_target": "Lan",
        "new_target": "Hà Nội",
        "segments": 2,
        "replacements": 3,
    }
    assert per[hanoi["id"]]["replacements"] == 1
    assert per[empty["id"]]["replacements"] == 0
    assert len(dry["samples"]) == 2
    s1 = next(s for s in dry["samples"] if s["chapter_index"] == 1)
    assert s1["variant_id"] == full_id and s1["title"]
    assert "Lan went to Hà Nội" in s1["before"] and "Hà Nội went to Sài Gòn" in s1["after"]
    assert _outputs(client, job_id) == before  # dry-run không ghi gì

    r = client.post(f"{API}/works/{wid}/names/apply", json={"changes": changes, "dry_run": False})
    assert r.status_code == 200, r.text
    applied = r.json()
    assert applied["batch_id"] is not None
    after = _outputs(client, job_id)
    assert "Hà Nội went to Sài Gòn. Hà Nội smiled." in after[1]
    assert "Lành said hi to Hà Nội" in after[2]  # "Lành" không bị đụng
    assert after[3] == before[3]

    gl = {g["id"]: g for g in client.get(f"{API}/works/{wid}/glossary").json()}
    assert gl[alice["id"]]["target_term"] == "Hà Nội"
    assert gl[hanoi["id"]]["target_term"] == "Sài Gòn"

    # Cache entry của segment cũng đổi theo (như PUT segment).
    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.repositories import (
        SegmentRepository,
        TranslationCacheRepository,
    )

    with SessionLocal() as db:
        seg = next(s for s in SegmentRepository(db).list_by_job(job_id) if s.chapter_index == 1)
        assert TranslationCacheRepository(db).get(seg.cache_key) == after[1]

    # Export đọc segment → thấy tên mới.
    txt = client.get(f"{API}/variants/{full_id}/export.txt").text
    assert "Hà Nội went to Sài Gòn" in txt and "Lan went" not in txt

    batches = client.get(f"{API}/works/{wid}/names/batches").json()
    assert batches[0]["id"] == applied["batch_id"]
    assert batches[0]["kind"] == "glossary"
    assert batches[0]["variant_id"] == full_id  # chỉ 1 variant được áp
    assert batches[0]["segments"] == 2
    assert {"old": "Lan", "new": "Hà Nội"} in batches[0]["changes"]

    # User sửa tay chương 2 sau khi áp → undo bỏ qua chương đó.
    seg2 = next(
        s for s in client.get(f"{API}/jobs/{job_id}/segments").json() if s["chapter_index"] == 2
    )
    assert client.put(
        f"{API}/segments/{seg2['id']}", json={"output_text": "sửa tay", "reviewed": True}
    ).status_code == 200

    r = client.post(f"{API}/works/{wid}/names/batches/{applied['batch_id']}/undo")
    assert r.status_code == 200, r.text
    assert r.json() == {"restored": 1, "skipped": 1}
    restored = _outputs(client, job_id)
    assert restored[1] == before[1]
    assert restored[2] == "sửa tay"
    gl = {g["id"]: g for g in client.get(f"{API}/works/{wid}/glossary").json()}
    assert gl[alice["id"]]["target_term"] == "Lan"
    assert gl[hanoi["id"]]["target_term"] == "Hà Nội"
    assert gl[empty["id"]]["target_term"] == ""
    assert client.get(f"{API}/works/{wid}/names/batches").json() == []
    assert client.post(f"{API}/works/{wid}/names/batches/{applied['batch_id']}/undo").status_code == 404


def test_names_apply_conflict_when_job_active(client):
    work = _import(client, "Names Busy", ["Alice."])
    wid = work["id"]
    full_id = work["variants"][0]["id"]
    alice = _add_term(client, wid, "Alice", "Lan", protected=True)
    _translate_full(client, work)

    from platform_.db import SessionLocal
    from translate.infrastructure.persistence.models import JobModel

    with SessionLocal() as db:
        busy = JobModel(variant_id=full_id, status="queued", provider="mock")
        db.add(busy)
        db.commit()
        busy_id = busy.id
    try:
        body = {"changes": [{"term_id": alice["id"], "new_target": "Mai"}], "dry_run": False}
        r = client.post(f"{API}/works/{wid}/names/apply", json=body)
        assert r.status_code == 409, r.text
        # dry-run vẫn xem trước được
        body["dry_run"] = True
        assert client.post(f"{API}/works/{wid}/names/apply", json=body).status_code == 200
        # variant không thuộc work → 404
        body["variant_ids"] = [999999]
        assert client.post(f"{API}/works/{wid}/names/apply", json=body).status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(JobModel).filter(JobModel.id == busy_id).delete()
            db.commit()


class _NamesHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        msgs = body.get("messages", [])
        system = next((m["content"] for m in msgs if m["role"] == "system"), "")
        user = next((m["content"] for m in msgs if m["role"] == "user"), "")
        type(self).calls.append({"system": system, "user": user})
        if "NAME REVIEW BOARD" in system:
            items = [{"source_term": "Alice", "target_term": "Ai Li", "kind": "character"}]
            for idx in re.findall(r"CHAPTER (\d+):", user):
                items.append({"source_term": f"Town{idx}x", "target_term": f"Trấn {idx}", "kind": "place"})
            reply = "```json\n" + json.dumps(items, ensure_ascii=False) + "\n```"
        else:
            reply = "[NO]"
        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_names_extract_samples_whole_book_and_adds_candidates(client):
    server = HTTPServer(("127.0.0.1", 0), _NamesHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        r = client.post(
            f"{API}/ai-providers",
            json={
                "label": "Names Fake",
                "kind": "local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "m",
                "api_key": "",
                "requires_api_key": False,
            },
        )
        assert r.status_code == 201, r.text
        ai_id = r.json()["id"]

        work = _import(client, "Names Extract", [f"Alice in Town{i}x. " + "x" * 1400 for i in range(1, 31)])
        wid = work["id"]
        _add_term(client, wid, "Alice", "Lan")  # đã có → không thêm trùng

        # Chưa có job, không chọn AI → 400.
        assert client.post(f"{API}/works/{wid}/names/extract", json={}).status_code == 400
        mock_id = next(p["id"] for p in client.get(f"{API}/ai-providers").json() if p["kind"] == "mock")
        assert client.post(
            f"{API}/works/{wid}/names/extract", json={"provider_id": mock_id}
        ).status_code == 400

        _NamesHandler.calls.clear()
        r = client.post(f"{API}/works/{wid}/names/extract", json={"provider_id": ai_id, "sample_chapters": 10})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["added"] == 10
        sampled = sorted(
            int(i) for c in _NamesHandler.calls for i in re.findall(r"CHAPTER (\d+):", c["user"])
        )
        assert len(sampled) == 10 and sampled[0] == 1 and sampled[-1] == 30  # rải đều cả sách
        assert 1 < len(_NamesHandler.calls) <= 4  # gộp vài lệnh gọi

        terms = {t["source_term"]: t for t in data["terms"]}
        assert terms["Alice"]["target_term"] == "Lan" and terms["Alice"]["status"] == "approved"
        town = terms["Town1x"]
        assert town["status"] == "candidate" and town["kind"] == "place"
        assert town["target_term"] == "Trấn 1" and town["source_chapter_count"] == 1

        # Có job rồi → không cần provider_id (lấy AI job gần nhất — ở đây là mock → 400).
        _translate_full(client, work)
        assert client.post(f"{API}/works/{wid}/names/extract", json={}).status_code == 400

        r = client.post(f"{API}/works/{wid}/names/approve", json={"term_ids": [town["id"]]})
        assert r.status_code == 200, r.text
        assert next(t for t in r.json() if t["id"] == town["id"])["status"] == "approved"
        assert client.post(f"{API}/works/{wid}/names/approve", json={"term_ids": [999999]}).status_code == 404

        # Áp tên cho term vừa duyệt cũng đặt status approved.
        cand = terms[f"Town{sampled[1]}x"]
        r = client.post(
            f"{API}/works/{wid}/names/apply",
            json={"changes": [{"term_id": cand["id"], "new_target": "Trấn Hai"}], "dry_run": False},
        )
        assert r.status_code == 200, r.text
        gl = {g["id"]: g for g in client.get(f"{API}/works/{wid}/glossary").json()}
        assert gl[cand["id"]]["status"] == "approved" and gl[cand["id"]]["target_term"] == "Trấn Hai"
    finally:
        server.shutdown()
        server.server_close()
