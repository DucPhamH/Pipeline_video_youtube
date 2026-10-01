"""Mode reskin ("giữ cốt, đổi vỏ") + bảng đổi vỏ theo variant."""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from translate.application.modes import (
    SKIN_MAP_PARAM,
    build_mode_instructions,
    normalize_mode_params,
    validate_mode,
)
from translate.application.segment_qa import QA_FLAGS, check_output
from translate.infrastructure.providers.openai_compat import skin_map_for_text

API = "/api/translate"


# --- Thuần (không DB) --------------------------------------------------------------


def test_reskin_params_defaults_and_validation():
    assert validate_mode("reskin") == "reskin"
    with pytest.raises(ValueError, match="reskin"):
        validate_mode("nope")
    p = normalize_mode_params("reskin", {"polish": True, "track_story_state": True})
    assert p == {"setting": "modern_urban", "intensity": "medium", "polish": True, "track_story_state": True}

    p = normalize_mode_params(
        "reskin",
        {"setting": "custom", "custom_setting": "Sài Gòn 1975", "intensity": "heavy",
         "keep_names": ["Lan", " Lan ", "", "Minh"], "notes": "giữ không khí buồn"},
    )
    assert p["custom_setting"] == "Sài Gòn 1975"
    assert p["keep_names"] == ["Lan", "Minh"]
    assert p["notes"] == "giữ không khí buồn"
    # custom_setting chỉ giữ khi setting=custom
    assert "custom_setting" not in normalize_mode_params("reskin", {"setting": "xianxia", "custom_setting": "x"})

    for bad in (
        {"setting": "mars"},
        {"setting": "custom"},
        {"setting": "custom", "custom_setting": "x" * 501},
        {"intensity": "extreme"},
        {"keep_names": [f"n{i}" for i in range(101)]},
        {"notes": "x" * 1001},
    ):
        with pytest.raises(ValueError):
            normalize_mode_params("reskin", bad)


def test_reskin_instructions_content():
    light = build_mode_instructions("reskin", {"setting": "school", "intensity": "light"}, already_translated=True)
    assert "school" in light and "LIGHT" in light
    assert "plot beat" in light and "MUST-KEEP BEATS" in light
    assert "SKIN MAP" in light and "VERBATIM" in light and "never output an original" in light
    heavy = build_mode_instructions(
        "reskin", {"setting": "custom", "custom_setting": "space opera", "intensity": "heavy",
                   "keep_names": ["Lan"]}, already_translated=True,
    )
    assert "space opera" in heavy and "HEAVY" in heavy and "Lan" in heavy


def test_skin_map_for_text_filters_by_original():
    params = {SKIN_MAP_PARAM: [["Lan", "Mai"], ["Hà Nội", "Đà Lạt"], ["Kiếm", ""]]}
    assert skin_map_for_text(params, "lan đi chợ") == [("Lan", "Mai")]  # không phân biệt hoa thường
    assert skin_map_for_text(params, "Không ai") == []
    assert skin_map_for_text({}, "Lan") == []


def test_qa_leftover_original_name():
    assert "leftover_original_name" in QA_FLAGS
    skin = [["Lan", "Mai"], ["Minh", "Minh"], ["An", "An Nhiên"]]
    kw = dict(source="", lang_src="vi", lang_tgt="vi", skin_map=skin)
    assert check_output(output="Lan cười.", mode="reskin", **kw) == ["leftover_original_name"]
    assert check_output(output="Mai cười, Lành mạnh.", mode="reskin", **kw) == []
    assert check_output(output="Minh cười.", mode="reskin", **kw) == []  # giữ nguyên tên
    assert check_output(output="An Nhiên cười.", mode="reskin", **kw) == []  # tên mới chứa tên gốc
    assert check_output(output="Lan cười.", mode="full", **kw) == []


# --- API + job --------------------------------------------------------------------------


class _ReskinHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []
    skin_reply: list[dict] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        msgs = body.get("messages", [])
        system = next((m["content"] for m in msgs if m["role"] == "system"), "")
        user = next((m["content"] for m in msgs if m["role"] == "user"), "")
        type(self).calls.append({"system": system, "user": user})
        if "You design a RESKIN" in system:
            reply = json.dumps(type(self).skin_reply, ensure_ascii=False)
        elif "meticulous story editor" in system:
            reply = "- beat một\n- beat hai"
        elif "Adaptation mode `reskin`" in system:
            reply = user
            if "GIỮ_GỐC" not in user:  # chương này "quên" đổi tên → QA gắn cờ
                for orig, repl in re.findall(r"^- (.+?) → (.+)$", system, re.M):
                    reply = reply.replace(orig, repl)
        else:
            reply = "[?]"
        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def fake_ai(client, monkeypatch):
    from translate.application import run_job

    monkeypatch.setattr(run_job, "MIN_CALL_INTERVAL", 0.0)
    server = HTTPServer(("127.0.0.1", 0), _ReskinHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    r = client.post(
        f"{API}/ai-providers",
        json={"label": f"Reskin Fake {port}", "kind": "local", "base_url": f"http://127.0.0.1:{port}/v1",
              "model": "m", "api_key": "", "requires_api_key": False},
    )
    assert r.status_code == 201, r.text
    _ReskinHandler.calls.clear()
    yield r.json()["id"]
    server.shutdown()
    server.server_close()


def _wait_job(client, job_id: int, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"{API}/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    return job


def _setup_work(client, title: str, chapters: list[str]):
    text = "\n\n".join(f"# Ch{i}\n\n{body}\n" for i, body in enumerate(chapters, 1))
    work = client.post(
        f"{API}/works/import-txt", json={"title": title, "lang_src": "en", "lang_tgt": "vi", "text": text}
    ).json()
    wid = work["id"]
    full_id = work["variants"][0]["id"]
    for src, tgt, kind in (("Alice", "Lan", "character"), ("Hanoi", "Hà Nội", "place"),
                           ("Bob", "Minh", "character")):
        assert client.post(
            f"{API}/works/{wid}/glossary",
            json={"source_term": src, "target_term": tgt, "protected": True, "kind": kind},
        ).status_code == 201
    r = client.post(f"{API}/variants/{full_id}/jobs", json={})
    assert _wait_job(client, r.json()["id"])["status"] == "completed"
    return wid, full_id


def _outputs(client, job_id):
    out = {}
    for s in client.get(f"{API}/jobs/{job_id}/segments").json():
        d = client.get(f"{API}/segments/{s['id']}").json()
        out[s["chapter_index"]] = d
    return out


def test_skin_map_crud_and_generate(client, fake_ai):
    wid, full_id = _setup_work(client, "Reskin CRUD", ["Alice lives in Hanoi with Bob."])
    r = client.post(f"{API}/works/{wid}/variants",
                    json={"mode": "reskin", "mode_params": {"setting": "xianxia", "keep_names": ["Minh"]}})
    assert r.status_code == 201, r.text
    rv = r.json()
    assert rv["source_variant_id"] == full_id and rv["mode_params"]["setting"] == "xianxia"
    vid = rv["id"]

    assert client.get(f"{API}/variants/{vid}/skin-map").json() == []
    # Bảng đổi vỏ chỉ cho reskin
    assert client.post(f"{API}/variants/{full_id}/skin-map",
                       json={"original": "Lan", "replacement": "X"}).status_code == 400
    assert client.post(f"{API}/variants/{vid}/skin-map",
                       json={"original": "Lan", "replacement": ""}).status_code == 400

    r = client.post(f"{API}/variants/{vid}/skin-map",
                    json={"original": "Lan", "replacement": "Lam Nhi", "kind": "character"})
    assert r.status_code == 201, r.text
    lan = r.json()
    assert lan == {"id": lan["id"], "original": "Lan", "replacement": "Lam Nhi", "kind": "character", "locked": False}
    assert client.post(f"{API}/variants/{vid}/skin-map",
                       json={"original": "Lan", "replacement": "Y"}).status_code == 400  # trùng

    r = client.put(f"{API}/variants/{vid}/skin-map/{lan['id']}", json={"locked": True})
    assert r.json()["locked"] is True and r.json()["replacement"] == "Lam Nhi"
    assert client.put(f"{API}/variants/{vid}/skin-map/{lan['id']}", json={"kind": "bad"}).status_code == 400

    _ReskinHandler.skin_reply = [
        {"original": "Lan", "replacement": "Tiên Nữ", "kind": "character"},
        {"original": "Hà Nội", "replacement": "Thanh Vân Tông", "kind": "place"},
        {"original": "Minh", "replacement": "Hắc Long", "kind": "character"},
    ]
    r = client.post(f"{API}/variants/{vid}/skin-map/generate", json={"provider_id": fake_ai})
    assert r.status_code == 200, r.text
    rows = {x["original"]: x for x in r.json()}
    assert rows["Lan"]["replacement"] == "Lam Nhi"  # locked không đổi
    assert rows["Hà Nội"]["replacement"] == "Thanh Vân Tông" and rows["Hà Nội"]["kind"] == "place"
    assert rows["Minh"]["replacement"] == "Minh"  # keep_names
    prompt = _ReskinHandler.calls[-1]
    assert "xianxia" in prompt["system"] and "- Lan (character)" in prompt["user"]

    # Không overwrite: chỉ điền dòng thiếu; overwrite: đổi dòng chưa khoá.
    _ReskinHandler.skin_reply = [{"original": "Hà Nội", "replacement": "Ma Giới", "kind": "place"},
                                 {"original": "Lan", "replacement": "Z", "kind": "character"}]
    rows = {x["original"]: x for x in client.post(
        f"{API}/variants/{vid}/skin-map/generate", json={"provider_id": fake_ai}).json()}
    assert rows["Hà Nội"]["replacement"] == "Thanh Vân Tông"
    rows = {x["original"]: x for x in client.post(
        f"{API}/variants/{vid}/skin-map/generate", json={"provider_id": fake_ai, "overwrite": True}).json()}
    assert rows["Hà Nội"]["replacement"] == "Ma Giới"
    assert rows["Lan"]["replacement"] == "Lam Nhi"

    hn = rows["Hà Nội"]
    assert client.delete(f"{API}/variants/{vid}/skin-map/{hn['id']}").status_code == 204
    assert client.delete(f"{API}/variants/{vid}/skin-map/{hn['id']}").status_code == 404
    assert len(client.get(f"{API}/variants/{vid}/skin-map").json()) == 2

    # Work chỉ có job mock, không chọn AI → 400.
    assert client.post(f"{API}/variants/{vid}/skin-map/generate", json={}).status_code == 400

    est_full = client.get(f"{API}/works/{wid}/estimate", params={"mode": "full"}).json()
    est_reskin = client.get(f"{API}/works/{wid}/estimate", params={"mode": "reskin"}).json()
    assert est_reskin["estimated_tokens"] > est_full["estimated_tokens"]  # thêm pass beats
    assert client.get(f"{API}/variants/{vid}/estimate").status_code == 200


def test_reskin_job_autogenerates_map_injects_relevant_entries_and_flags_leftovers(client, fake_ai):
    wid, full_id = _setup_work(
        client, "Reskin Job",
        ["Alice lives in Hanoi.", "Bob waits. GIỮ_GỐC Alice", "Nobody here."],
    )
    vid = client.post(f"{API}/works/{wid}/variants",
                      json={"mode": "reskin", "mode_params": {"setting": "modern_urban", "intensity": "light"}}).json()["id"]
    _ReskinHandler.skin_reply = [
        {"original": "Lan", "replacement": "Linh", "kind": "character"},
        {"original": "Hà Nội", "replacement": "Thành phố B", "kind": "place"},
        {"original": "Minh", "replacement": "Khoa", "kind": "character"},
    ]
    r = client.post(f"{API}/variants/{vid}/jobs", json={"ai_provider_id": fake_ai})
    assert r.status_code == 202, r.text
    job = _wait_job(client, r.json()["id"])
    assert job["status"] == "completed", job

    # Bảng tự sinh khi job bắt đầu.
    rows = {x["original"]: x["replacement"] for x in client.get(f"{API}/variants/{vid}/skin-map").json()}
    assert rows == {"Lan": "Linh", "Hà Nội": "Thành phố B", "Minh": "Khoa"}

    outs = _outputs(client, job["id"])
    assert "Linh lives in Thành phố B" in outs[1]["output_text"]
    assert outs[1]["qa_flags"] == []
    assert outs[1]["status"] == "done"
    # Chương 2 còn tên gốc "Lan" → DONE nhưng gắn cờ.
    assert outs[2]["status"] == "done"
    assert "leftover_original_name" in outs[2]["qa_flags"]

    rewrite_calls = [c for c in _ReskinHandler.calls if "Adaptation mode `reskin`" in c["system"]]
    assert len(rewrite_calls) == 3
    ch1 = next(c for c in rewrite_calls if "lives in" in c["user"])
    assert "SKIN MAP" in ch1["system"] and "- Lan → Linh" in ch1["system"]
    assert "Minh → Khoa" not in ch1["system"]  # chỉ mục liên quan tới chương
    assert "MUST-KEEP BEATS (preserve all, in order):" in ch1["system"]
    assert "beat một" in ch1["system"]
    assert "Glossary (apply" not in ch1["system"]  # glossary tên bản full không vào reskin
    ch3 = next(c for c in rewrite_calls if "Nobody" in c["user"])
    assert "SKIN MAP (" not in ch3["system"]
    beats_calls = [c for c in _ReskinHandler.calls if "meticulous story editor" in c["system"]]
    assert len(beats_calls) == 3

    # Cache key phụ thuộc bảng đổi vỏ.
    from platform_.db import SessionLocal
    from translate.application.modes import mode_params_hash
    from translate.application.skin_map import effective_mode_params
    from translate.infrastructure.persistence.repositories import VariantRepository

    with SessionLocal() as db:
        v = VariantRepository(db).get(vid)
        h1 = mode_params_hash(effective_mode_params(db, v))
    row = next(x for x in client.get(f"{API}/variants/{vid}/skin-map").json() if x["original"] == "Minh")
    client.put(f"{API}/variants/{vid}/skin-map/{row['id']}", json={"replacement": "Khoa Học"})
    with SessionLocal() as db:
        v = VariantRepository(db).get(vid)
        assert mode_params_hash(effective_mode_params(db, v)) != h1

    # Áp đổi vỏ lên chương đã reskin (không dịch lại) + undo qua batches của Work.
    linh = next(x for x in client.get(f"{API}/variants/{vid}/skin-map").json() if x["original"] == "Lan")
    body = {"changes": [{"row_id": linh["id"], "new_replacement": "Ngọc"}], "dry_run": True}
    dry = client.post(f"{API}/variants/{vid}/skin-map/apply", json=body).json()
    assert dry["batch_id"] is None and dry["total_replacements"] == 1
    assert dry["per_term"][0] == {"term_id": linh["id"], "old_target": "Linh", "new_target": "Ngọc",
                                  "segments": 1, "replacements": 1}
    assert client.post(f"{API}/variants/{vid}/skin-map/apply",
                       json={"changes": [{"row_id": linh["id"], "new_replacement": ""}], "dry_run": True}
                       ).status_code == 422
    body["dry_run"] = False
    applied = client.post(f"{API}/variants/{vid}/skin-map/apply", json=body).json()
    assert applied["batch_id"]
    assert "Ngọc lives in" in _outputs(client, job["id"])[1]["output_text"]
    rows = {x["original"]: x["replacement"] for x in client.get(f"{API}/variants/{vid}/skin-map").json()}
    assert rows["Lan"] == "Ngọc"
    batch = client.get(f"{API}/works/{wid}/names/batches").json()[0]
    assert batch["kind"] == "skin_map" and batch["variant_id"] == vid
    assert batch["changes"] == [{"old": "Linh", "new": "Ngọc"}]

    r = client.post(f"{API}/works/{wid}/names/batches/{applied['batch_id']}/undo")
    assert r.json() == {"restored": 1, "skipped": 0}
    assert "Linh lives in" in _outputs(client, job["id"])[1]["output_text"]
    rows = {x["original"]: x["replacement"] for x in client.get(f"{API}/variants/{vid}/skin-map").json()}
    assert rows["Lan"] == "Linh"

    # Đổi tên glossary trên bản full → original trong bảng đổi vỏ đi theo; undo trả lại.
    gl = {g["source_term"]: g for g in client.get(f"{API}/works/{wid}/glossary").json()}
    r = client.post(f"{API}/works/{wid}/names/apply",
                    json={"changes": [{"term_id": gl["Alice"]["id"], "new_target": "Lan Anh"}],
                          "variant_ids": [full_id], "dry_run": False})
    assert r.status_code == 200, r.text
    originals = {x["original"] for x in client.get(f"{API}/variants/{vid}/skin-map").json()}
    assert "Lan Anh" in originals and "Lan" not in originals
    client.post(f"{API}/works/{wid}/names/batches/{r.json()['batch_id']}/undo")
    originals = {x["original"] for x in client.get(f"{API}/variants/{vid}/skin-map").json()}
    assert "Lan" in originals and "Lan Anh" not in originals


def test_reskin_mock_job_without_map(client):
    """AI mock không tự sinh bảng — job vẫn chạy, mock vẫn qua luồng reskin."""
    wid, _ = _setup_work(client, "Reskin Mock", ["Alice smiles."])
    vid = client.post(f"{API}/works/{wid}/variants", json={"mode": "reskin"}).json()["id"]
    client.post(f"{API}/variants/{vid}/skin-map", json={"original": "Lan", "replacement": "Vy"})
    r = client.post(f"{API}/variants/{vid}/jobs", json={})
    job = _wait_job(client, r.json()["id"])
    assert job["status"] == "completed", job
    out = list(_outputs(client, job["id"]).values())[0]["output_text"]
    assert out.startswith("[fork+reskin] (reskin:modern_urban)") and "Vy smiles" in out
