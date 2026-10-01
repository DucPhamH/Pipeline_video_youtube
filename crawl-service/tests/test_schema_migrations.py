"""DB cũ thiếu cột vẫn được ALTER, và chạy lại không lỗi."""
from sqlalchemy import create_engine, text

from platform_.migrate import apply_migrations


def test_old_novels_table_gains_columns_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE novels (id INTEGER PRIMARY KEY, title VARCHAR(255))"))

    apply_migrations(engine)
    apply_migrations(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(novels)"))}
        versions = [row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))]
    assert {"author", "cover_url", "content_fingerprint"} <= cols
    assert versions == [1, 2, 3, 4]


def test_old_db_gains_lookup_indexes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old2.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE novels (id INTEGER PRIMARY KEY, title VARCHAR(255))"))
        conn.execute(
            text(
                "CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER, "
                "chapter_index INTEGER, source_url VARCHAR(500))"
            )
        )
        # DB đã áp migration 1 từ trước (cột có, index chưa có).
        conn.execute(
            text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
        )
        conn.execute(
            text("ALTER TABLE novels ADD COLUMN content_fingerprint VARCHAR(64) DEFAULT ''")
        )
        conn.execute(text("INSERT INTO schema_migrations VALUES (1, 'x', 'now')"))

    apply_migrations(engine)
    apply_migrations(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT type, name FROM sqlite_master WHERE type='index'"))
        idx = {row[1] for row in rows}
    assert {"ix_novel_content_fingerprint", "ix_chapter_novel_source_url"} <= idx


def test_old_chapters_table_gains_toc_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old3.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER, "
                "chapter_index INTEGER, source_url VARCHAR(500))"
            )
        )
    apply_migrations(engine)
    apply_migrations(engine)
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(chapters)"))}
        rows = conn.execute(text("SELECT type, name FROM sqlite_master WHERE type='index'"))
        idx = {row[1] for row in rows}
    assert "toc_order" in cols
    assert "ix_chapter_novel_toc_order" in idx
