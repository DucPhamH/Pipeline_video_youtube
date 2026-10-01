"""Thêm cột trên bảng đã tồn tại. create_all không làm việc này.

Mỗi bước ghi một dòng vào schema_migrations. Chạy lại thì bỏ qua bước đã áp.
"""
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


def _novel_extra_columns(conn: Connection) -> None:
    _add_column(conn, "novels", "author", "ALTER TABLE novels ADD COLUMN author VARCHAR(255) DEFAULT ''")
    _add_column(
        conn,
        "novels",
        "cover_url",
        "ALTER TABLE novels ADD COLUMN cover_url VARCHAR(500) DEFAULT ''",
    )
    _add_column(
        conn,
        "novels",
        "content_fingerprint",
        "ALTER TABLE novels ADD COLUMN content_fingerprint VARCHAR(64) DEFAULT ''",
    )


def _create_index(conn: Connection, name: str, table: str, columns: list[str]) -> None:
    """CREATE INDEX IF NOT EXISTS — bỏ qua nếu bảng/cột chưa có."""
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    names = {row[1] for row in rows}
    if not rows or not set(columns) <= names:
        return
    cols = ", ".join(columns)
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))


def _lookup_indexes(conn: Connection) -> None:
    # Migration 1 thêm cột nhưng DB cũ không có index (create_all không đụng bảng đã có).
    _create_index(conn, "ix_novel_content_fingerprint", "novels", ["content_fingerprint"])
    # Resume/sync so khớp chương theo URL. Không UNIQUE: dữ liệu cũ có thể trùng
    # URL (TOC biquge lặp khối chương mới nhất).
    _create_index(conn, "ix_chapter_novel_source_url", "chapters", ["novel_id", "source_url"])


def _follow_audio_columns(conn: Connection) -> None:
    _add_column(
        conn,
        "novel_follows",
        "auto_audio",
        "ALTER TABLE novel_follows ADD COLUMN auto_audio INTEGER DEFAULT 0",
    )
    _add_column(
        conn,
        "novel_follows",
        "voice_preset",
        "ALTER TABLE novel_follows ADD COLUMN voice_preset VARCHAR(40) DEFAULT 'nam_ke'",
    )
    _add_column(
        conn,
        "novel_follows",
        "translate_variant_id",
        "ALTER TABLE novel_follows ADD COLUMN translate_variant_id INTEGER",
    )
    _add_column(
        conn,
        "novel_follows",
        "tts_work_id",
        "ALTER TABLE novel_follows ADD COLUMN tts_work_id INTEGER",
    )


def _chapter_toc_order(conn: Connection) -> None:
    # Vị trí chương trong mục lục site lần sync gần nhất — sắp xếp đọc/xuất
    # theo cột này (chapter_index giữ làm định danh ổn định; chương chèn giữa
    # TOC được lưu ở index trống cuối nên không dùng để sắp xếp được).
    _add_column(conn, "chapters", "toc_order", "ALTER TABLE chapters ADD COLUMN toc_order INTEGER")
    _create_index(conn, "ix_chapter_novel_toc_order", "chapters", ["novel_id", "toc_order"])


MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "novel author, cover_url, content_fingerprint", _novel_extra_columns),
    (2, "index novel content_fingerprint, chapter (novel_id, source_url)", _lookup_indexes),
    (3, "chapter toc_order", _chapter_toc_order),
    (4, "follow auto audio", _follow_audio_columns),
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
