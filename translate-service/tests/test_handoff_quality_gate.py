"""B2 (spec mục 6) — gate chất lượng handoff: translate-service KHÔNG tự chặn
dịch (crawl-service đã có require_cleaned riêng trước khi gọi handoff), nhưng
phải lưu + trả lại missing_cleaned/unreviewed_chapters để FE cảnh báo."""


def test_from_crawl_stores_and_updates_quality_counts(client):
    payload = {
        "external_id": "crawl:novel:quality-gate-demo",
        "title": "Quality Gate Demo",
        "author": "A",
        "lang_src": "zh",
        "lang_tgt_hint": "vi",
        "chapters": [
            {"index": 1, "title": "Ch1", "text": "一", "fingerprint": "fp1", "has_cleaned": False, "reviewed": False},
            {"index": 2, "title": "Ch2", "text": "二", "fingerprint": "fp2", "has_cleaned": True, "reviewed": False},
        ],
        "missing_cleaned": 1,
        "unreviewed": 2,
    }
    r = client.post("/api/translate/works/from-crawl", json=payload)
    assert r.status_code == 200, r.text
    work = r.json()
    assert work["missing_cleaned"] == 1
    assert work["unreviewed_chapters"] == 2
    work_id = work["id"]

    # Không bị chặn tạo/kiểm tra Work dù còn thiếu cleaned/review
    r = client.get(f"/api/translate/works/{work_id}")
    assert r.status_code == 200
    assert r.json()["missing_cleaned"] == 1

    # Không cũng KHÔNG chặn start job — chỉ là cảnh báo hiển thị, không phải hard gate
    variant_id = work["variants"][0]["id"]
    r = client.post(f"/api/translate/variants/{variant_id}/jobs")
    assert r.status_code == 202, r.text

    # Re-sync với dữ liệu đã sạch hơn -> số liệu cập nhật theo lần gửi mới nhất
    payload["missing_cleaned"] = 0
    payload["unreviewed"] = 1
    r = client.post("/api/translate/works/from-crawl", json=payload)
    assert r.status_code == 200, r.text
    synced = r.json()
    assert synced["created"] is False
    assert synced["missing_cleaned"] == 0
    assert synced["unreviewed_chapters"] == 1


def test_from_crawl_defaults_quality_counts_to_zero_when_omitted(client):
    r = client.post(
        "/api/translate/works/from-crawl",
        json={
            "external_id": "crawl:novel:quality-gate-default",
            "title": "No Counts Sent",
            "lang_src": "zh",
            "lang_tgt_hint": "vi",
            "chapters": [{"index": 1, "title": "Ch1", "text": "内容", "fingerprint": "fpx"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["missing_cleaned"] == 0
    assert r.json()["unreviewed_chapters"] == 0
