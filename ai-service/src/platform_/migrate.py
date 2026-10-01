"""Thêm cột trên bảng đã tồn tại. create_all không làm việc này."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS: list[tuple[int, str, object]] = []


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
