"""Verify `GET /novels` phân trang + lọc theo NGUỒN (source_key) + tìm kiếm
— trước đây trả hết 1 mảng phẳng, không tách được truyện theo site (mục
9.5)."""
from crawl.domain.entities import Novel
from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository


def _seed_novels(db, *, source_key: str, count: int, title_prefix: str = "Truyện") -> None:
    repo = SqlAlchemyNovelRepository(db)
    for i in range(count):
        repo.add(
            Novel(
                id=None,
                title=f"{title_prefix} {source_key} {i}",
                source_key=source_key,
                source_url=f"http://x/{source_key}/{title_prefix}-{i}",
            )
        )


def test_list_novels_filters_by_source_key(client):  # noqa: ARG001
    db = _db()
    try:
        _seed_novels(db, source_key="pg_test_site_a", count=3)
        _seed_novels(db, source_key="pg_test_site_b", count=2)

        r = client.get("/api/crawl/novels", params={"source_key": "pg_test_site_a", "limit": 50})
        data = r.json()
        assert data["total"] == 3
        assert all(n["source_key"] == "pg_test_site_a" for n in data["items"])

        r2 = client.get("/api/crawl/novels", params={"source_key": "pg_test_site_b", "limit": 50})
        data2 = r2.json()
        assert data2["total"] == 2
    finally:
        db.close()


def test_list_novels_paginates_with_limit_and_offset(client):  # noqa: ARG001
    db = _db()
    try:
        _seed_novels(db, source_key="pg_test_site_c", count=5)

        page1 = client.get(
            "/api/crawl/novels", params={"source_key": "pg_test_site_c", "limit": 2, "offset": 0}
        ).json()
        page2 = client.get(
            "/api/crawl/novels", params={"source_key": "pg_test_site_c", "limit": 2, "offset": 2}
        ).json()
        page3 = client.get(
            "/api/crawl/novels", params={"source_key": "pg_test_site_c", "limit": 2, "offset": 4}
        ).json()

        assert page1["total"] == page2["total"] == page3["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        assert len(page3["items"]) == 1  # phần dư

        # 3 trang không trùng lặp bản ghi nào.
        ids = [n["id"] for n in page1["items"] + page2["items"] + page3["items"]]
        assert len(ids) == len(set(ids)) == 5
    finally:
        db.close()


def test_list_novels_search_filters_by_title(client):  # noqa: ARG001
    db = _db()
    try:
        _seed_novels(db, source_key="pg_test_site_d", count=1, title_prefix="Kiếm Hiệp Kỳ Duyên")
        _seed_novels(db, source_key="pg_test_site_d", count=1, title_prefix="Đô Thị Dị Năng")

        r = client.get(
            "/api/crawl/novels", params={"source_key": "pg_test_site_d", "search": "Kiếm Hiệp", "limit": 50}
        )
        data = r.json()
        assert data["total"] == 1
        assert "Kiếm Hiệp" in data["items"][0]["title"]
    finally:
        db.close()


def test_list_novels_limit_capped_at_100(client):  # noqa: ARG001
    r = client.get("/api/crawl/novels", params={"limit": 9999})
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 100


def test_list_novels_filters_by_is_manual(client):  # noqa: ARG001
    db = _db()
    try:
        repo = SqlAlchemyNovelRepository(db)
        repo.add(
            Novel(
                id=None, title="Quét thể loại", source_key="pg_manual_f",
                source_url="http://x/pg_manual_f/scan", is_manual=False,
            )
        )
        repo.add(
            Novel(
                id=None, title="Thêm URL", source_key="pg_manual_f",
                source_url="http://x/pg_manual_f/url", is_manual=True,
            )
        )

        scanned = client.get(
            "/api/crawl/novels",
            params={"source_key": "pg_manual_f", "is_manual": False, "limit": 50},
        ).json()
        assert scanned["total"] == 1
        assert scanned["items"][0]["is_manual"] is False

        manual = client.get(
            "/api/crawl/novels",
            params={"source_key": "pg_manual_f", "is_manual": True, "limit": 50},
        ).json()
        assert manual["total"] == 1
        assert manual["items"][0]["is_manual"] is True
    finally:
        db.close()


def test_list_novels_filters_by_genre_id(client):  # noqa: ARG001
    db = _db()
    try:
        from crawl.infrastructure.persistence.repositories import SqlAlchemyGenreRepository

        genre_repo = SqlAlchemyGenreRepository(db)
        g1 = genre_repo.get_or_create(
            source_key="pg_genre_novel",
            genre_key="test_a",
            label="Thể loại A",
            list_url="http://x/a",
        )
        g2 = genre_repo.get_or_create(
            source_key="pg_genre_novel",
            genre_key="test_b",
            label="Thể loại B",
            list_url="http://x/b",
        )
        novel_repo = SqlAlchemyNovelRepository(db)
        novel_repo.add(
            Novel(
                id=None, title="Truyện A", source_key="pg_genre_novel",
                source_url="http://x/pg_genre_novel/a", genre_id=g1.id, is_manual=False,
            )
        )
        novel_repo.add(
            Novel(
                id=None, title="Truyện B", source_key="pg_genre_novel",
                source_url="http://x/pg_genre_novel/b", genre_id=g2.id, is_manual=False,
            )
        )

        filtered = client.get(
            "/api/crawl/novels",
            params={"source_key": "pg_genre_novel", "genre_id": g1.id, "limit": 50},
        ).json()
        assert filtered["total"] == 1
        assert filtered["items"][0]["title"] == "Truyện A"
        assert filtered["items"][0]["genre_id"] == g1.id
    finally:
        db.close()


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
