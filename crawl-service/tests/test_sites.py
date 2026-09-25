"""Verify `GET /sites` — trang "Danh sách site" mới (mục 9.0): chỉ liệt kê
site THẬT, bỏ nguồn nội bộ dùng để test (`demo_local`, `is_test=True`)."""


def test_list_sites_excludes_test_only_sources(client):
    r = client.get("/api/crawl/sites", params={"limit": 100})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data and "total" in data
    sites = data["items"]
    keys = {s["key"] for s in sites}

    assert "demo_local" not in keys
    assert "biquge_pro" not in keys
    assert "bqgxs_com" in keys
    assert "bgq99_cc" in keys
    assert "fsshu_com" in keys
    assert "biquge365_net" in keys
    assert "powanjuan_cc" in keys
    assert "zw85_com" in keys
    assert "biqvgeu_cc" in keys
    assert "trxs_cc" in keys
    assert "qbtr_cc" in keys
    assert "faloo_com" in keys
    assert "piaotia_com" in keys
    assert "linovelib_com" in keys
    assert "n17k_com" in keys
    assert "wenku8_net" in keys
    assert "ciweimao_com" in keys
    assert "qidian_com" in keys
    for s in sites:
        assert set(s.keys()) == {"key", "name", "access_kind", "region"}
        assert s["access_kind"] in {"free", "session_optional", "session_required"}
        assert s["region"] in {"china", "japan", "korea", "vietnam", "taiwan"}
    assert "syosetu_com" in keys
    assert "kakuyomu_com" in keys
    assert "novelba_com" in keys
    assert "daysneo_com" in keys
    assert "novelpia_com" in keys
    assert "truyenfull_vn" in keys
    assert "truyenfull_today" in keys
    assert "dtruyen_com" in keys
    assert "sstruyen_net" in keys
    assert "docln_net" in keys
    assert "esjzone_cc" in keys
    assert "zhihu_com" in keys
    assert "ixdzs_tw" in keys
    assert "syosetu_com" in keys
    assert "jjwxc_net" in keys
    assert "zongheng_com" in keys


def test_list_sites_filters_by_access_kind(client):
    free = client.get("/api/crawl/sites", params={"access_kind": "free", "limit": 100}).json()
    assert free["total"] >= 10
    assert all(s["access_kind"] == "free" for s in free["items"])
    assert "bqgxs_com" in {s["key"] for s in free["items"]}

    needs = client.get("/api/crawl/sites", params={"access_kind": "needs_session", "limit": 100}).json()
    keys = {s["key"] for s in needs["items"]}
    assert "qidian_com" in keys
    assert "wenku8_net" in keys
    assert "bqgxs_com" not in keys
    assert all(s["access_kind"] != "free" for s in needs["items"])

    required = client.get(
        "/api/crawl/sites", params={"access_kind": "session_required", "limit": 100}
    ).json()
    assert {s["key"] for s in required["items"]} >= {"qidian_com", "wenku8_net"}


def test_list_sites_filters_by_region(client):
    japan = client.get("/api/crawl/sites", params={"region": "japan", "limit": 100}).json()
    assert japan["total"] >= 5
    assert all(s["region"] == "japan" for s in japan["items"])
    assert "syosetu_com" in {s["key"] for s in japan["items"]}
    assert "kakuyomu_com" in {s["key"] for s in japan["items"]}
    assert "novelba_com" in {s["key"] for s in japan["items"]}
    assert "daysneo_com" in {s["key"] for s in japan["items"]}
    assert "linovelib_com" in {s["key"] for s in japan["items"]}

    taiwan = client.get("/api/crawl/sites", params={"region": "taiwan", "limit": 100}).json()
    assert taiwan["total"] >= 4
    assert all(s["region"] == "taiwan" for s in taiwan["items"])
    assert "eights_tw_com" in {s["key"] for s in taiwan["items"]}
    assert "ixdzs_tw" in {s["key"] for s in taiwan["items"]}
    assert "ttkan_co" in {s["key"] for s in taiwan["items"]}
    assert "quanben_io" in {s["key"] for s in taiwan["items"]}

    vietnam = client.get("/api/crawl/sites", params={"region": "vietnam", "limit": 100}).json()
    vn_keys = {s["key"] for s in vietnam["items"]}
    assert vietnam["total"] >= 5
    assert all(s["region"] == "vietnam" for s in vietnam["items"])
    assert vn_keys >= {
        "truyenfull_vn",
        "truyenfull_today",
        "dtruyen_com",
        "sstruyen_net",
        "docln_net",
    }

    china = client.get("/api/crawl/sites", params={"region": "china", "limit": 100}).json()
    assert china["total"] >= 15
    assert "bqgxs_com" in {s["key"] for s in china["items"]}


def test_list_sites_paginates_and_searches(client):
    r = client.get("/api/crawl/sites", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    page1 = r.json()
    assert len(page1["items"]) <= 2
    assert page1["total"] >= len(page1["items"])

    r2 = client.get("/api/crawl/sites", params={"search": "bqgxs", "limit": 50})
    data2 = r2.json()
    assert data2["total"] >= 1
    assert all("bqgxs" in s["key"].casefold() or "bqgxs" in s["name"].casefold() for s in data2["items"])


def test_per_site_settings_seeded_independently_per_source(client):
    """Mỗi site seed sẵn 1 bộ setting quét riêng — đổi site này không đụng
    site khác (mục 9.0)."""
    values = client.get("/api/crawl/settings").json()["values"]

    assert values["crawl.scan_window.bqgxs_com"] == 5
    assert values["crawl.narration_filter.bqgxs_com"] == "first_person"

    client.patch("/api/crawl/settings", json={"values": {"crawl.scan_window.bqgxs_com": 42}})
    values_after = client.get("/api/crawl/settings").json()["values"]
    assert values_after["crawl.scan_window.bqgxs_com"] == 42
    assert values_after["crawl.scan_window.bgq99_cc"] == 5  # site khác không bị đụng

    # Trả lại giá trị cũ để không ảnh hưởng test khác chạy sau.
    client.patch("/api/crawl/settings", json={"values": {"crawl.scan_window.bqgxs_com": 5}})
