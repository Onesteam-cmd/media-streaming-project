from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.db.session import engine
from app.models import tables  # noqa: F401


def _ensure_column(table_name: str, column_name: str, column_sql: str) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        existing_columns = {row[1] for row in rows}

        if column_name not in existing_columns:
            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
            )


def _ensure_media_candidate_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(media_candidates)").fetchall()
        existing_columns = {row[1] for row in rows}

        columns = {
            "quality_label": "VARCHAR(100)",
            "audio_label": "VARCHAR(100)",
            "rank_score": "INTEGER",
        }

        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE media_candidates ADD COLUMN {column_name} {column_type}"
                )


def _ensure_ingest_job_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(ingest_jobs)").fetchall()
        existing_columns = {row[1] for row in rows}

        columns = {
            "external_id": "VARCHAR(128)",
        }

        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE ingest_jobs ADD COLUMN {column_name} {column_type}"
                )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_media_candidate_columns()
    _ensure_ingest_job_columns()

    if engine.url.get_backend_name() == "sqlite":
        _ensure_column("media_candidates", "item_identifier", "VARCHAR(512)")
        _ensure_column("media_candidates", "download_url", "VARCHAR(2048)")
        _ensure_column("media_candidates", "file_size", "INTEGER")
        _ensure_column("media_candidates", "seeders", "INTEGER")
        _ensure_column("media_candidates", "peers", "INTEGER")
        _ensure_column("media_candidates", "estimated_download_seconds", "INTEGER")
        _ensure_column("media_requests", "user_id", "VARCHAR(128) DEFAULT 'default'")

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE media_requests SET user_id = 'default' WHERE user_id IS NULL OR user_id = ''")
            )

def ensure_media_candidate_duration_column() -> None:
    from app.db.session import engine

    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(media_candidates)")).fetchall()
        columns = {row[1] for row in rows}

        if "duration_seconds" not in columns:
            conn.execute(text("ALTER TABLE media_candidates ADD COLUMN duration_seconds INTEGER"))

