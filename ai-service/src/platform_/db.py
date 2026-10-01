from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
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
    from platform_.migrate import apply_migrations
    from ai.infrastructure.persistence import models as ai_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    apply_migrations(engine)
