"""DB cũ thiếu cột vẫn được ALTER, và chạy lại không lỗi."""
from sqlalchemy import create_engine, text

from platform_.migrate import apply_migrations


def test_old_readings_table_gains_columns_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE readings (id INTEGER PRIMARY KEY)"))

    apply_migrations(engine)
    apply_migrations(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(readings)"))}
        versions = [row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))]
    assert {"dialogue_voice", "pitch", "volume", "style", "male_voice", "female_voice", "use_cast", "provider_id", "device"} <= cols
    assert versions == [1, 2, 3]
