from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def new_id() -> str:
    return str(uuid4())


class UserTable(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuthSessionTable(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WatchPositionTable(Base):
    __tablename__ = "watch_positions"
    __table_args__ = (
        UniqueConstraint("user_id", "media_id", name="uq_watch_positions_user_media"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    media_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)



class MediaStreamTokenTable(Base):
    __tablename__ = "media_stream_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class MediaCandidateTable(Base):
    __tablename__ = "media_candidates"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    license_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    relative_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    item_identifier: Mapped[str | None] = mapped_column(String(512), nullable=True)
    download_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seeders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_download_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rank_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class MediaRequestTable(Base):
    __tablename__ = "media_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default", index=True)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class IngestJobTable(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    adapter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
