"""1 AI (1 nhà cung cấp) được chọn NHIỀU API KEY khác nhau, CÙNG 1 model — kiểu
AiNiee/Glossarion (xoay nhiều tài khoản/key để né rate-limit; đã bỏ hẳn trục
"nhiều model/1 AI" sau khi xác nhận thật với Gemini là vẫn tính chung 1 hạn
mức tài khoản dù đổi model, chỉ đổi key mới thực sự né được rate-limit)."""
import time


def _add_ai_with_keys(client, label: str, model: str, api_keys: list[str]) -> int:
    r = client.post(
        "/api/translate/ai-providers",
        json={
            "label": label,
            "kind": "mock",
            "base_url": "",
            "model": model,
            "api_key": api_keys[0],
            "api_keys": api_keys,
            "requires_api_key": False,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key_count"] == len(api_keys)
    return body["id"]


def _wait_job(client, job_id: int, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/translate/jobs/{job_id}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    return status


def test_ai_provider_saves_and_returns_multiple_keys(client):
    ai_id = _add_ai_with_keys(client, "Gemini Multi Key", "gemini-flash-latest", ["key-aaaa1111", "key-bbbb2222"])
    got = client.get("/api/translate/ai-providers").json()
    row = next(p for p in got if p["id"] == ai_id)
    assert row["key_count"] == 2
    assert len(row["api_key_hints"]) == 2
    assert row["api_key_hints"][0] != row["api_key_hints"][1]

    # Patch chỉ đổi key đơn -> tự thêm vào đầu danh sách api_keys, không mất key cũ
    r = client.put(f"/api/translate/ai-providers/{ai_id}", json={"api_key": "key-cccc3333"})
    assert r.status_code == 200, r.text
    assert r.json()["key_count"] == 3


def test_add_and_delete_key_by_index_do_not_need_raw_value_roundtrip(client):
    """Key là secret — client chỉ thấy hint bị che, không thể gửi lại nguyên
    vẹn qua PUT full-replace. Endpoint add/delete riêng cho phép quản lý key
    mà không bao giờ cần client biết giá trị thật của key cũ."""
    ai_id = _add_ai_with_keys(client, "Add/Delete Key AI", "m", ["key-first"])

    r = client.post(f"/api/translate/ai-providers/{ai_id}/keys", json={"api_key": "key-second"})
    assert r.status_code == 201, r.text
    assert r.json()["key_count"] == 2

    r = client.post(f"/api/translate/ai-providers/{ai_id}/keys", json={"api_key": "key-third"})
    assert r.status_code == 201, r.text
    assert r.json()["key_count"] == 3

    # Xoá key ở giữa (index 1 = "key-second") — 2 key còn lại vẫn nguyên vẹn,
    # không cần client từng biết giá trị thật của chúng.
    r = client.delete(f"/api/translate/ai-providers/{ai_id}/keys/1")
    assert r.status_code == 200, r.text
    assert r.json()["key_count"] == 2

    r = client.delete(f"/api/translate/ai-providers/{ai_id}/keys/99")
    assert r.status_code == 404


def test_one_ai_multiple_keys_becomes_multiple_slots_same_model(client):
    ai_id = _add_ai_with_keys(client, "Gemini Multi Key 2", "gemini-flash-latest", ["key-aaaa", "key-bbbb"])

    text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, 5))  # 4 chương
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Multi Key Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    variant_id = r.json()["variants"][0]["id"]

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={
            "ai_selections": [{"ai_provider_id": ai_id, "api_keys": ["key-aaaa", "key-bbbb"]}],
            "ai_mode": "pool",
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    job_id = job["id"]
    # 2 key đã chọn -> 2 slot, CÙNG 1 model (khác test multi-model — model đổi)
    assert len(job["provider_slots"]) == 2
    models_in_slots = {s["model"] for s in job["provider_slots"]}
    assert models_in_slots == {"gemini-flash-latest"}
    labels = {s["label"] for s in job["provider_slots"]}
    assert any("key…aaaa" in lb for lb in labels)
    assert any("key…bbbb" in lb for lb in labels)

    assert _wait_job(client, job_id) == "completed"
    segs = client.get(f"/api/translate/jobs/{job_id}/segments").json()
    assert len(segs) == 4
    assert all(s["status"] in ("done", "skipped_cache") for s in segs)


def test_use_all_keys_flag_via_http_api_does_not_need_literal_keys(client):
    """FE không bao giờ biết giá trị key thật (chỉ có hint bị che) — nên FE gửi
    `use_all_keys: true` thay vì literal `api_keys`; server tự đọc TẤT CẢ key
    đã lưu từ registry. Test này đi qua đúng HTTP API (không gọi enqueue_job
    trực tiếp) để khớp với đường đi thật của FE."""
    ai_id = _add_ai_with_keys(client, "Use All Keys AI", "gemini-flash-latest", ["key-x1", "key-x2", "key-x3"])

    text = "\n\n".join(f"# Ch{i}\n\nBody {i}." for i in range(1, 4))
    r = client.post(
        "/api/translate/works/import-txt",
        json={"title": "Use All Keys Demo", "lang_src": "en", "lang_tgt": "vi", "text": text},
    )
    variant_id = r.json()["variants"][0]["id"]

    r = client.post(
        f"/api/translate/variants/{variant_id}/jobs",
        json={"ai_selections": [{"ai_provider_id": ai_id, "use_all_keys": True}], "ai_mode": "pool"},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert len(job["provider_slots"]) == 3
    assert {s["model"] for s in job["provider_slots"]} == {"gemini-flash-latest"}

    assert _wait_job(client, job["id"]) == "completed"
