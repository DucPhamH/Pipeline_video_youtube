"""Verify tính năng "select box mỗi site 1 thể loại": chọn 1 thể loại làm
active tự động tắt các thể loại khác CÙNG site, không đụng thể loại của
site khác."""
from crawl.application.use_cases import SetActiveGenreUseCase
from crawl.infrastructure.persistence.repositories import SqlAlchemyGenreRepository


def test_activating_genre_disables_siblings_same_site(client):  # noqa: ARG001
    genre_repo = SqlAlchemyGenreRepository(_db())
    try:
        a = genre_repo.get_or_create(source_key="site_x", genre_key="g1", label="G1", list_url="u1")
        b = genre_repo.get_or_create(source_key="site_x", genre_key="g2", label="G2", list_url="u2")
        # get_or_create mặc định enabled=True -> cả 2 đang bật (mô phỏng
        # trạng thái cũ trước khi có ràng buộc "1 site 1 active").
        assert a.enabled is True
        assert b.enabled is True

        use_case = SetActiveGenreUseCase(genre_repo)
        result = use_case.execute(b.id)

        assert result.enabled is True
        a_after = genre_repo.get_by_id(a.id)
        b_after = genre_repo.get_by_id(b.id)
        assert a_after.enabled is False  # bị tắt vì cùng site với b
        assert b_after.enabled is True
    finally:
        genre_repo.db.close()


def test_activating_hot_ranking_option_disables_regular_genre_same_site(client):  # noqa: ARG001
    """1 site chỉ ĐÚNG 1 lựa chọn active — kể cả option "Hot nhất (mọi thể
    loại)" cũng nằm CHUNG danh sách PHẲNG, chọn nó tắt thể loại đang bật và
    ngược lại (sửa 17/9/2026, 2 lần: bỏ "kind" tách select box độc lập theo
    phản hồi thật "sao vẫn chia làm 2 block", rồi bỏ tiếp "family_key" gộp
    cặp "Thể loại"+"Sắp xếp" — giờ chỉ còn ĐÚNG 1 select PHẲNG/site)."""
    genre_repo = SqlAlchemyGenreRepository(_db())
    try:
        genre = genre_repo.get_or_create(
            source_key="site_w", genre_key="horror", label="Kinh dị", list_url="u1"
        )
        hot = genre_repo.get_or_create(source_key="site_w", genre_key="hot", label="Hot nhất", list_url="u2")
        use_case = SetActiveGenreUseCase(genre_repo)

        use_case.execute(hot.id)
        assert genre_repo.get_by_id(hot.id).enabled is True

        use_case.execute(genre.id)
        assert genre_repo.get_by_id(genre.id).enabled is True
        assert genre_repo.get_by_id(hot.id).enabled is False  # bị tắt, cùng site
    finally:
        genre_repo.db.close()


def test_activating_genre_does_not_affect_other_sites(client):  # noqa: ARG001
    genre_repo = SqlAlchemyGenreRepository(_db())
    try:
        x = genre_repo.get_or_create(source_key="site_y", genre_key="g1", label="G1", list_url="u1")
        y = genre_repo.get_or_create(source_key="site_z", genre_key="g1", label="G1", list_url="u1")

        use_case = SetActiveGenreUseCase(genre_repo)
        use_case.execute(x.id)

        # x và y khác source_key -> không đụng nhau.
        assert genre_repo.get_by_id(x.id).enabled is True
        assert genre_repo.get_by_id(y.id).enabled is True
    finally:
        genre_repo.db.close()


def test_set_active_genre_returns_none_for_missing_id(client):  # noqa: ARG001
    genre_repo = SqlAlchemyGenreRepository(_db())
    try:
        use_case = SetActiveGenreUseCase(genre_repo)
        assert use_case.execute(999999) is None
    finally:
        genre_repo.db.close()


def _db():
    from platform_.db import SessionLocal

    return SessionLocal()
