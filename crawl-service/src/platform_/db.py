from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from platform_.config import config

# SQLite cần connect_args đặc biệt để dùng chung connection giữa các thread
# (FastAPI + APScheduler chạy job nền). Bỏ qua nếu sau này đổi Postgres.
_is_sqlite = config.database_url.startswith("sqlite")
# timeout (giây): SQLite đợi lock thay vì fail ngay — crawl nền + API ghi song song.
# Tăng 60s vì crawl có thể giữ write ngắn; vẫn fail nếu txn khác kẹt lâu.
_connect_args = {"check_same_thread": False, "timeout": 60.0} if _is_sqlite else {}

# NullPool: mỗi session = 1 connection mới — tránh pool giữ connection đang
# pending transaction giữa các thread (dễ "database is locked" với SQLite).
_engine_kwargs: dict = {"connect_args": _connect_args}
if _is_sqlite:
    _engine_kwargs["poolclass"] = NullPool
engine = create_engine(config.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:
        # WAL + busy_timeout: giảm write-lock khi crawl (nhiều commit) và
        # thread nền/API đọc song song — pattern novel-downloader / production SQLite.
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


def commit_with_busy_retry(db: Session, *, retries: int = 10) -> None:
    """Commit với retry khi SQLite báo locked/busy.

    Lưu ý: sau lỗi, SQLAlchemy bắt rollback — chỉ dùng khi caller sẵn sàng
    mất pending state HOẶC khi không còn dirty object cần giữ (vd vừa flush
    xong và commit ngay). Với INSERT mới, hãy retry cả vòng add ở repository.
    """
    import time

    from sqlalchemy.exc import OperationalError

    delay = 0.05
    last: Exception | None = None
    for attempt in range(retries):
        try:
            db.commit()
            return
        except OperationalError as exc:
            last = exc
            msg = str(exc).lower()
            db.rollback()
            if "locked" not in msg and "busy" not in msg:
                raise
            if attempt >= retries - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 2.0)
    assert last is not None
    raise last


def is_sqlite_locked(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


def _ensure_sqlite_novel_columns() -> None:
    """create_all không ALTER cột mới trên bảng đã tồn tại — bổ sung author/
    cover_url/content_fingerprint nếu DB cũ thiếu."""
    if not _is_sqlite:
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(novels)")).fetchall()
        cols = {row[1] for row in rows}
        alters = [
            ("author", "ALTER TABLE novels ADD COLUMN author VARCHAR(255) DEFAULT ''"),
            ("cover_url", "ALTER TABLE novels ADD COLUMN cover_url VARCHAR(500) DEFAULT ''"),
            (
                "content_fingerprint",
                "ALTER TABLE novels ADD COLUMN content_fingerprint VARCHAR(64) DEFAULT ''",
            ),
        ]
        for name, ddl in alters:
            if name not in cols:
                conn.execute(text(ddl))


def init_db():
    # Import mọi module models.py của từng context để đăng ký bảng trước
    # khi create_all — mỗi context tự thêm dòng import ở đây khi có bảng mới.
    from crawl.infrastructure.persistence import models as crawl_models  # noqa: F401
    from platform_ import settings_store  # noqa: F401  (bảng Settings key-value)

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_novel_columns()
