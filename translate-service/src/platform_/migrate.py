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


def _translate_columns(conn: Connection) -> None:
    _add_column(conn, "segments", "reviewed", "ALTER TABLE segments ADD COLUMN reviewed INTEGER DEFAULT 0")
    _add_column(conn, "segments", "slot_index", "ALTER TABLE segments ADD COLUMN slot_index INTEGER DEFAULT 0")
    _add_column(conn, "segments", "story_state", "ALTER TABLE segments ADD COLUMN story_state TEXT DEFAULT ''")
    _add_column(conn, "works", "callback_url", "ALTER TABLE works ADD COLUMN callback_url VARCHAR(500)")
    _add_column(
        conn, "works", "missing_cleaned", "ALTER TABLE works ADD COLUMN missing_cleaned INTEGER DEFAULT 0"
    )
    _add_column(
        conn,
        "works",
        "unreviewed_chapters",
        "ALTER TABLE works ADD COLUMN unreviewed_chapters INTEGER DEFAULT 0",
    )
    _add_column(conn, "variants", "mode_params", "ALTER TABLE variants ADD COLUMN mode_params JSON")
    _add_column(
        conn,
        "variants",
        "source_variant_id",
        "ALTER TABLE variants ADD COLUMN source_variant_id INTEGER",
    )
    _add_column(conn, "jobs", "base_url", "ALTER TABLE jobs ADD COLUMN base_url VARCHAR(500) DEFAULT ''")
    _add_column(conn, "jobs", "api_key", "ALTER TABLE jobs ADD COLUMN api_key VARCHAR(500) DEFAULT ''")
    _add_column(
        conn,
        "jobs",
        "requires_api_key",
        "ALTER TABLE jobs ADD COLUMN requires_api_key INTEGER DEFAULT 1",
    )
    _add_column(conn, "jobs", "ai_provider_id", "ALTER TABLE jobs ADD COLUMN ai_provider_id INTEGER")
    _add_column(
        conn, "jobs", "ai_mode", "ALTER TABLE jobs ADD COLUMN ai_mode VARCHAR(20) DEFAULT 'single'"
    )
    _add_column(conn, "jobs", "api_keys_json", "ALTER TABLE jobs ADD COLUMN api_keys_json TEXT DEFAULT '[]'")
    _add_column(
        conn,
        "job_provider_slots",
        "ai_provider_id",
        "ALTER TABLE job_provider_slots ADD COLUMN ai_provider_id INTEGER",
    )
    _add_column(
        conn,
        "ai_providers",
        "api_keys_json",
        "ALTER TABLE ai_providers ADD COLUMN api_keys_json TEXT DEFAULT '[]'",
    )


def _segment_qa_flags(conn: Connection) -> None:
    _add_column(conn, "segments", "qa_flags", "ALTER TABLE segments ADD COLUMN qa_flags TEXT")


def _glossary_review_columns(conn: Connection) -> None:
    _add_column(
        conn, "glossary_terms", "kind", "ALTER TABLE glossary_terms ADD COLUMN kind VARCHAR(20) DEFAULT ''"
    )
    # Dòng cũ coi như đã duyệt — giữ hành vi prompt như trước.
    _add_column(
        conn,
        "glossary_terms",
        "status",
        "ALTER TABLE glossary_terms ADD COLUMN status VARCHAR(20) DEFAULT 'approved'",
    )


MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "columns added after the first translate schema", _translate_columns),
    (2, "segments.qa_flags (output QA)", _segment_qa_flags),
    (3, "glossary_terms.kind/status (bảng duyệt tên)", _glossary_review_columns),
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
