"""DB cũ thiếu cột vẫn được ALTER, và chạy lại không lỗi."""
from sqlalchemy import create_engine, text

from platform_.migrate import apply_migrations


def test_old_segments_table_gains_columns_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE segments (id INTEGER PRIMARY KEY)"))

    apply_migrations(engine)
    apply_migrations(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(segments)"))}
        versions = [row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))]
    assert {"reviewed", "slot_index", "story_state", "qa_flags"} <= cols
    assert versions == [1, 2, 3]


def test_old_glossary_rows_become_approved(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old_gl.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE glossary_terms (id INTEGER PRIMARY KEY, work_id INTEGER, "
                "source_term VARCHAR(255), target_term VARCHAR(255), protected INTEGER, notes VARCHAR(500))"
            )
        )
        conn.execute(text("INSERT INTO glossary_terms (work_id, source_term, target_term) VALUES (1, 'A', 'B')"))

    apply_migrations(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT kind, status FROM glossary_terms")).one()
    assert tuple(row) == ("", "approved")
