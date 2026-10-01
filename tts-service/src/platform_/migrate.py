"""Thêm cột trên bảng đã tồn tại. create_all không làm việc này."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


def _add_column(conn: Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    if not rows:
        return
    names = {row[1] for row in rows}
    if column not in names:
        conn.execute(text(ddl))


def _tts_columns(conn: Connection) -> None:
    _add_column(
        conn,
        "readings",
        "dialogue_voice",
        "ALTER TABLE readings ADD COLUMN dialogue_voice VARCHAR(120) DEFAULT ''",
    )
    _add_column(conn, "readings", "pitch", "ALTER TABLE readings ADD COLUMN pitch VARCHAR(20) DEFAULT '+0Hz'")
    _add_column(
        conn, "readings", "volume", "ALTER TABLE readings ADD COLUMN volume VARCHAR(20) DEFAULT '+0%'"
    )
    _add_column(conn, "readings", "style", "ALTER TABLE readings ADD COLUMN style VARCHAR(40) DEFAULT ''")
    _add_column(
        conn,
        "jobs",
        "dialogue_voice",
        "ALTER TABLE jobs ADD COLUMN dialogue_voice VARCHAR(120) DEFAULT ''",
    )
    _add_column(conn, "jobs", "pitch", "ALTER TABLE jobs ADD COLUMN pitch VARCHAR(20) DEFAULT '+0Hz'")
    _add_column(conn, "jobs", "volume", "ALTER TABLE jobs ADD COLUMN volume VARCHAR(20) DEFAULT '+0%'")
    _add_column(conn, "jobs", "style", "ALTER TABLE jobs ADD COLUMN style VARCHAR(40) DEFAULT ''")
    _add_column(conn, "works", "cover_path", "ALTER TABLE works ADD COLUMN cover_path VARCHAR(300) DEFAULT ''")


def _cast_columns(conn: Connection) -> None:
    for table in ("readings", "jobs"):
        _add_column(
            conn,
            table,
            "male_voice",
            f"ALTER TABLE {table} ADD COLUMN male_voice VARCHAR(120) DEFAULT ''",
        )
        _add_column(
            conn,
            table,
            "female_voice",
            f"ALTER TABLE {table} ADD COLUMN female_voice VARCHAR(120) DEFAULT ''",
        )
        _add_column(
            conn,
            table,
            "use_cast",
            f"ALTER TABLE {table} ADD COLUMN use_cast INTEGER DEFAULT 0",
        )
        _add_column(
            conn,
            table,
            "provider_id",
            f"ALTER TABLE {table} ADD COLUMN provider_id INTEGER",
        )
    _add_column(
        conn,
        "segments",
        "pieces_json",
        "ALTER TABLE segments ADD COLUMN pieces_json TEXT DEFAULT ''",
    )


def _device_column(conn: Connection) -> None:
    for table in ("readings", "jobs"):
        _add_column(
            conn,
            table,
            "device",
            f"ALTER TABLE {table} ADD COLUMN device VARCHAR(10) DEFAULT 'cpu'",
        )


MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "voice params and cover added after the first tts schema", _tts_columns),
    (2, "cast voices and tagged chapter pieces", _cast_columns),
    (3, "vieneu cpu or gpu", _device_column),
]


def apply_migrations(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
        )
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
        now = datetime.now(timezone.utc).isoformat()
        for version, name, step in MIGRATIONS:
            if version in applied:
                continue
            step(conn)  # type: ignore[operator]
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, name, applied_at) "
                    "VALUES (:version, :name, :applied_at)"
                ),
                {"version": version, "name": name, "applied_at": now},
            )
