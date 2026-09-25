"""Verify `GET /genres` phân trang + lọc — dùng thể loại seed sẵn trong catalog."""


def test_list_genres_paginates_with_limit_and_offset(client):
    r = client.get(
        "/api/crawl/genres",
        params={"source_key": "bqgxs_com", "limit": 2, "offset": 0},
    )
    assert r.status_code == 200
    page1 = r.json()
    assert page1["total"] >= 4
    assert len(page1["items"]) == 2

    page2 = client.get(
        "/api/crawl/genres",
        params={"source_key": "bqgxs_com", "limit": 2, "offset": 2},
    ).json()
    assert page2["total"] == page1["total"]
    ids = [g["id"] for g in page1["items"] + page2["items"]]
    assert len(set(ids)) == 4


def test_list_genres_search_filters_by_label(client):
    r = client.get(
        "/api/crawl/genres",
        params={"source_key": "bqgxs_com", "search": "fantasy", "limit": 50},
    ).json()
    assert r["total"] >= 1
    assert all(
        "fantasy" in g["label"].casefold() or "fantasy" in g["genre_key"].casefold() for g in r["items"]
    )


def test_list_genres_filters_by_enabled(client):
    genres = client.get(
        "/api/crawl/genres", params={"source_key": "bqgxs_com", "limit": 50}
    ).json()["items"]
    assert len(genres) >= 2
    target = genres[0]
    client.patch(f"/api/crawl/genres/{target['id']}", json={"enabled": True})

    enabled = client.get(
        "/api/crawl/genres",
        params={"source_key": "bqgxs_com", "enabled": True, "limit": 50},
    ).json()
    assert enabled["total"] == 1
    assert enabled["items"][0]["id"] == target["id"]


def test_list_genres_filters_by_last_run_status(client):
    all_genres = client.get(
        "/api/crawl/genres", params={"source_key": "bqgxs_com", "limit": 50}
    ).json()
    assert all_genres["total"] >= 1
    sample_status = all_genres["items"][0]["last_run_status"]

    filtered = client.get(
        "/api/crawl/genres",
        params={"source_key": "bqgxs_com", "last_run_status": sample_status, "limit": 50},
    ).json()
    assert filtered["total"] >= 1
    assert all(g["last_run_status"] == sample_status for g in filtered["items"])
    assert filtered["total"] <= all_genres["total"]
