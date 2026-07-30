from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


settings = get_settings()

connect_args = {}
engine_kwargs = {}

if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30
    engine_kwargs["poolclass"] = NullPool

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    cursor = dbapi_connection.cursor()

    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
