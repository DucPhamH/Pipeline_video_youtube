"""Select thể loại = đúng số thể loại thật trên từng site — không tự chế."""
from collections import defaultdict

from crawl.infrastructure.sources.registry import GENRE_SEEDS, catalog_genre_keys


def test_shared_genre_key_across_sites_uses_consistent_vietnamese_label():
    by_genre_key: dict[str, set[str]] = defaultdict(set)
    for s in GENRE_SEEDS:
        vietnamese_prefix = s["label"].split(" (")[0].strip()
        # Bỏ prefix "Tìm kiếm: " khi so sánh khái niệm Kinh dị vs horror_search
        vietnamese_prefix = vietnamese_prefix.removeprefix("Tìm kiếm: ").strip()
        by_genre_key[s["genre_key"]].add(vietnamese_prefix)

    inconsistent = {key: labels for key, labels in by_genre_key.items() if len(labels) > 1}
    assert inconsistent == {}, f"genre_key dùng nhãn KHÁC NHAU giữa các site: {inconsistent}"


def test_no_fabricated_hot_variants_in_catalog():
    """Không nhân đôi thể loại thành bản Hot — select chỉ có trang thể loại thật."""
    keys = [s["genre_key"] for s in GENRE_SEEDS]
    assert not any(k.endswith("_hot") for k in keys)
    assert "hot" not in keys


def test_each_site_genre_count_matches_real_nav_categories():
    """Mỗi site: số thể loại = đúng nav thật (không bịa thêm)."""
    by_source: dict[str, list[str]] = defaultdict(list)
    for s in GENRE_SEEDS:
        by_source[s["source_key"]].append(s["genre_key"])

    assert "biquge_pro" not in by_source
    assert len(by_source["bqgxs_com"]) == 9
    assert "horror_search" in by_source["bqgxs_com"]
    assert "urban" in by_source["bqgxs_com"]
    assert "military" not in by_source["bqgxs_com"]  # site không có — không bịa

    assert len(by_source["bgq99_cc"]) == 7
    assert len(by_source["fsshu_com"]) == 8
    assert len(by_source["biquge365_net"]) == 8
    assert "horror" in by_source["biquge365_net"]
    assert len(by_source["powanjuan_cc"]) == 8
    assert "horror" in by_source["powanjuan_cc"]
    assert len(by_source["zw85_com"]) == 6
    assert len(by_source["biqvgeu_cc"]) == 7
    assert len(by_source["diandingnnn_cc"]) == 7
    assert len(by_source["eights_tw_com"]) == 5
    assert len(by_source["bqg2_com"]) == 8
    assert len(by_source["bqge_cc"]) == 6
    assert len(by_source["bxg123_cc"]) == 5
    assert by_source["trxs_cc"] == ["fanfic"]
    assert by_source["qbtr_cc"] == ["fanfic", "other"]
    assert len(by_source["faloo_com"]) == 9
    assert "horror" in by_source["faloo_com"]
    assert "fanfic" in by_source["faloo_com"]
    assert len(by_source["piaotia_com"]) == 9
    assert "horror" in by_source["piaotia_com"]
    assert by_source["linovelib_com"] == ["other"]
    assert len(by_source["n17k_com"]) == 8
    assert "fantasy" in by_source["n17k_com"]
    assert len(by_source["wenku8_net"]) == 8
    assert "fantasy" in by_source["wenku8_net"]
    assert len(by_source["ciweimao_com"]) == 8
    assert "fanfic" in by_source["ciweimao_com"]
    assert len(by_source["qidian_com"]) == 8
    assert "fantasy" in by_source["qidian_com"]

    assert len(by_source["syosetu_com"]) == 6
    assert len(by_source["kakuyomu_com"]) == 3
    assert len(by_source["novelba_com"]) == 6
    assert len(by_source["daysneo_com"]) == 5
    assert len(by_source["novelpia_com"]) == 5
    assert len(by_source["truyenfull_vn"]) == 9
    assert len(by_source["truyenfull_today"]) == 9
    assert len(by_source["dtruyen_com"]) == 9
    assert len(by_source["sstruyen_net"]) == 9
    assert len(by_source["docln_net"]) == 5
    assert len(by_source["esjzone_cc"]) == 5
    assert len(by_source["zhihu_com"]) == 1
    assert len(by_source["ixdzs_tw"]) == 7
    assert len(by_source["ttkan_co"]) == 10
    assert len(by_source["quanben_io"]) == 11
    assert len(by_source["syosetu_com"]) == 6
    assert len(by_source["jjwxc_net"]) == 7
    assert len(by_source["zongheng_com"]) == 8


def test_genres_endpoint_filters_to_catalog_only(client):
    allowed = catalog_genre_keys()
    r = client.get("/api/crawl/genres", params={"limit": 200})
    assert r.status_code == 200
    for g in r.json()["items"]:
        assert (g["source_key"], g["genre_key"]) in allowed
        assert "family_key" not in g
        assert not g["genre_key"].endswith("_hot")


def test_genres_endpoint_scoped_by_source_key(client):
    r = client.get("/api/crawl/genres", params={"source_key": "bqgxs_com", "limit": 50})
    assert r.status_code == 200
    items = r.json()["items"]
    keys = {g["genre_key"] for g in items}
    assert "horror_search" in keys
    assert "fantasy" in keys
    assert all(g["source_key"] == "bqgxs_com" for g in items)
    assert len(keys) == 9