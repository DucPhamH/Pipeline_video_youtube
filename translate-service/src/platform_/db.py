from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from platform_.config import config

_is_sqlite = config.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False, "timeout": 60.0} if _is_sqlite else {}

_engine_kwargs: dict = {"connect_args": _connect_args}
if _is_sqlite:
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(config.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from translate.infrastructure.persistence import models as translate_models  # noqa: F401
    from platform_ import settings_store  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if _is_sqlite:
        _sqlite_add_missing_columns()


def _sqlite_add_missing_columns() -> None:
    """create_all không thêm cột mới — ALTER nhẹ cho DB đã có."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "segments" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("segments")}
        with engine.begin() as conn:
            if "reviewed" not in cols:
                conn.execute(text("ALTER TABLE segments ADD COLUMN reviewed INTEGER DEFAULT 0"))
            if "slot_index" not in cols:
                conn.execute(text("ALTER TABLE segments ADD COLUMN slot_index INTEGER DEFAULT 0"))
            if "story_state" not in cols:
                conn.execute(text("ALTER TABLE segments ADD COLUMN story_state TEXT DEFAULT ''"))
    if "works" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("works")}
        with engine.begin() as conn:
            if "callback_url" not in cols:
                conn.execute(text("ALTER TABLE works ADD COLUMN callback_url VARCHAR(500)"))
            if "missing_cleaned" not in cols:
                conn.execute(text("ALTER TABLE works ADD COLUMN missing_cleaned INTEGER DEFAULT 0"))
            if "unreviewed_chapters" not in cols:
                conn.execute(
                    text("ALTER TABLE works ADD COLUMN unreviewed_chapters INTEGER DEFAULT 0")
                )
    if "variants" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("variants")}
        with engine.begin() as conn:
            if "mode_params" not in cols:
                conn.execute(text("ALTER TABLE variants ADD COLUMN mode_params JSON"))
            if "source_variant_id" not in cols:
                conn.execute(
                    text("ALTER TABLE variants ADD COLUMN source_variant_id INTEGER")
                )
    if "jobs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("jobs")}
        with engine.begin() as conn:
            if "base_url" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN base_url VARCHAR(500) DEFAULT ''"))
            if "api_key" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN api_key VARCHAR(500) DEFAULT ''"))
            if "requires_api_key" not in cols:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN requires_api_key INTEGER DEFAULT 1")
                )
            if "ai_provider_id" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_provider_id INTEGER"))
            if "ai_mode" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_mode VARCHAR(20) DEFAULT 'single'"))
            if "api_keys_json" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN api_keys_json TEXT DEFAULT '[]'"))
    if "job_provider_slots" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("job_provider_slots")}
        with engine.begin() as conn:
            if "ai_provider_id" not in cols:
                conn.execute(text("ALTER TABLE job_provider_slots ADD COLUMN ai_provider_id INTEGER"))
    if "ai_providers" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_providers")}
        with engine.begin() as conn:
            if "api_keys_json" not in cols:
                conn.execute(text("ALTER TABLE ai_providers ADD COLUMN api_keys_json TEXT DEFAULT '[]'"))

