"""Retry hàng loạt novel error (sau cập nhật cookie / lỗ VIP)."""
from crawl.domain.entities import Novel, NovelLifecycle
from crawl.infrastructure.persistence.repositories import SqlAlchemyNovelRepository
from platform_.db import SessionLocal
from platform_.locks import wait_until_idle


def test_retry_errors_queues_error_novels(client):
    db = SessionLocal()
    try:
        repo = SqlAlchemyNovelRepository(db)
        n1 = repo.add(
            Novel(
                id=None,
                title="Error A",
                source_key="demo_local",
                source_url="http://demo.local/err-a",
                lifecycle_status=NovelLifecycle.ERROR,
                error_message="Thiếu 2 chương — VIP",
                last_chapter_index=1,
                total_chapters=3,
            )
        )
        n2 = repo.add(
            Novel(
                id=None,
                title="Error B",
                source_key="demo_local",
                source_url="http://demo.local/err-b",
                lifecycle_status=NovelLifecycle.ERROR,
                error_message="VIP",
                last_chapter_index=0,
                total_chapters=2,
            )
        )
        # Không xếp hàng: khác status
        repo.add(
            Novel(
                id=None,
                title="OK",
                source_key="demo_local",
                source_url="http://demo.local/ok",
                lifecycle_status=NovelLifecycle.FULLY_CRAWLED,
                last_chapter_index=2,
                total_chapters=2,
            )
        )
        # Không xếp hàng: khác site
        repo.add(
            Novel(
                id=None,
                title="Other site",
                source_key="bqgxs_com",
                source_url="http://other/err",
                lifecycle_status=NovelLifecycle.ERROR,
                error_message="x",
            )
        )
    finally:
        db.close()

    r = client.post(
        "/api/crawl/novels/retry-errors",
        json={"source_key": "demo_local", "limit": 50},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["queued"] >= 2
    assert n1.id in body["novel_ids"]
    assert n2.id in body["novel_ids"]

    # KHÔNG check "đang crawling" ở đây (bug test thật phát hiện 17/9/2026,
    # không phải bug sản phẩm): `demo_local` với URL giả fail GẦN NHƯ TỨC
    # THỜI (`list_chapters()` raise ngay, không có độ trễ mạng thật), và
    # `_retry_errors_sequential` xử lý n1 RỒI MỚI TỚI n2 trong CÙNG 1 thread
    # — không có gì đảm bảo cả 2 novel CÙNG lúc ở "crawling" khi request GET
    # này chạy tới (n1 có thể đã xong lại về "error" trước khi n2 kịp bắt
    # đầu) — assertion cũ dựa vào 1 khung thời gian không thật sự tồn tại
    # nên fail ngẫu nhiên tuỳ tốc độ máy. Đợi thread nền xong HẲN
    # (`wait_until_idle`) rồi assert kết quả CUỐI CÙNG mới đáng tin.
    wait_until_idle()
    db2 = SessionLocal()
    try:
        repo2 = SqlAlchemyNovelRepository(db2)
        n1_after = repo2.get_by_id(n1.id)
        n2_after = repo2.get_by_id(n2.id)
        # Cả 2 đều ĐÃ được xử lý thật (error_message đổi khác bản seed ban
        # đầu, vì demo_local không tìm thấy file chương ở URL giả — không
        # còn giữ nguyên lý do lỗi CŨ, chứng tỏ có crawl lại thật chứ không
        # bỏ qua).
        assert n1_after.error_message != "Thiếu 2 chương — VIP"
        assert n2_after.error_message != "VIP"
    finally:
        db2.close()


def test_retry_errors_unknown_source(client):
    r = client.post(
        "/api/crawl/novels/retry-errors",
        json={"source_key": "no_such_source_xyz"},
    )
    assert r.status_code == 404
