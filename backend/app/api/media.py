from datetime import datetime, timedelta
from pathlib import Path
import mimetypes
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.tables import (
    MediaCandidateTable,
    MediaRequestTable,
    MediaStreamTokenTable,
)
from app.services.user_context import get_current_user_id


router = APIRouter(prefix="/api/media", tags=["media"])


def _safe_media_file_path(relative_path: str) -> Path:
    settings = get_settings()
    media_root = Path(settings.media_root).resolve()
    file_path = (media_root / relative_path).resolve()

    try:
        file_path.relative_to(media_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Недопустимый путь к файлу.") from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")

    return file_path


def _delete_expired_stream_tokens(db: Session, now: datetime) -> None:
    for stream_token in db.scalars(
        select(MediaStreamTokenTable).where(MediaStreamTokenTable.expires_at <= now)
    ).all():
        db.delete(stream_token)


def _create_stream_token(
    db: Session,
    user_id: str,
    candidate_id: str,
) -> str:
    settings = get_settings()
    now = datetime.utcnow()

    _delete_expired_stream_tokens(db, now)

    token = secrets.token_urlsafe(32)

    db.add(
        MediaStreamTokenTable(
            token=token,
            user_id=user_id,
            candidate_id=candidate_id,
            created_at=now,
            expires_at=now + timedelta(minutes=max(1, settings.media_stream_token_ttl_minutes)),
        )
    )

    db.commit()

    return token


def _prepared_media_item(
    request: Request,
    db: Session,
    user_id: str,
    row: MediaCandidateTable,
) -> dict:
    relative_path = row.relative_path

    if not relative_path:
        raise ValueError("Candidate has no relative_path")

    token = _create_stream_token(
        db=db,
        user_id=user_id,
        candidate_id=row.id,
    )

    stream_path = f"/api/media/stream/{quote(row.id, safe='')}?token={quote(token, safe='')}"
    stream_url = str(request.base_url).rstrip("/") + stream_path

    return {
        "id": row.id,
        "title": row.title,
        "source": row.source,
        "year": row.year,
        "file_name": row.file_name,
        "relative_path": relative_path,
        "stream_path": stream_path,
        "stream_url": stream_url,
    }


@router.get("/prepared")
def list_prepared_media(
    request: Request,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    request_rows = db.scalars(
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .where(MediaRequestTable.status == "completed")
        .order_by(MediaRequestTable.updated_at.desc())
    ).all()

    items = []
    seen_candidate_ids: set[str] = set()

    for request_row in request_rows:
        if request_row.candidate_id in seen_candidate_ids:
            continue

        seen_candidate_ids.add(request_row.candidate_id)

        row = db.get(MediaCandidateTable, request_row.candidate_id)

        if row is None or not row.relative_path:
            continue

        items.append(
            _prepared_media_item(
                request=request,
                db=db,
                user_id=current_user_id,
                row=row,
            )
        )

    return {
        "count": len(items),
        "items": items,
    }


@router.get("/stream/{candidate_id}", name="stream_prepared_media")
def stream_prepared_media(
    candidate_id: str,
    token: str,
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    stream_token = db.scalars(
        select(MediaStreamTokenTable)
        .where(MediaStreamTokenTable.token == token)
        .where(MediaStreamTokenTable.candidate_id == candidate_id)
        .where(MediaStreamTokenTable.expires_at > now)
    ).first()

    if stream_token is None:
        raise HTTPException(
            status_code=401,
            detail="Ссылка на просмотр недействительна или истекла.",
        )

    user_has_media = db.scalar(
        select(func.count())
        .select_from(MediaRequestTable)
        .where(MediaRequestTable.user_id == stream_token.user_id)
        .where(MediaRequestTable.candidate_id == candidate_id)
        .where(MediaRequestTable.status == "completed")
    ) or 0

    if user_has_media <= 0:
        raise HTTPException(status_code=404, detail="Фильм не найден в медиатеке.")

    row = db.get(MediaCandidateTable, candidate_id)

    if row is None or not row.relative_path:
        raise HTTPException(status_code=404, detail="Фильм не найден.")

    file_path = _safe_media_file_path(row.relative_path)
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=row.file_name or file_path.name,
    )


@router.delete("/prepared/{candidate_id}")
def delete_prepared_media(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    row = db.get(MediaCandidateTable, candidate_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Фильм не найден.",
        )

    user_requests = db.scalars(
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .where(MediaRequestTable.candidate_id == candidate_id)
        .where(MediaRequestTable.status == "completed")
    ).all()

    if not user_requests:
        raise HTTPException(
            status_code=404,
            detail="Фильм не найден в медиатеке текущего аккаунта.",
        )

    for request in user_requests:
        request.status = "deleted"
        request.updated_at = datetime.utcnow()

    db.scalars(
        select(MediaStreamTokenTable)
        .where(MediaStreamTokenTable.user_id == current_user_id)
        .where(MediaStreamTokenTable.candidate_id == candidate_id)
    ).all()

    for stream_token in db.scalars(
        select(MediaStreamTokenTable)
        .where(MediaStreamTokenTable.user_id == current_user_id)
        .where(MediaStreamTokenTable.candidate_id == candidate_id)
    ).all():
        db.delete(stream_token)

    other_completed_count = db.scalar(
        select(func.count())
        .select_from(MediaRequestTable)
        .where(MediaRequestTable.candidate_id == candidate_id)
        .where(MediaRequestTable.status == "completed")
        .where(MediaRequestTable.user_id != current_user_id)
    ) or 0

    deleted_files: list[str] = []

    if other_completed_count <= 0:
        settings = get_settings()
        media_root = Path(settings.media_root).resolve()
        movies_dir = Path(settings.movies_dir).resolve()

        paths_to_delete: set[Path] = set()

        if row.relative_path:
            paths_to_delete.add((media_root / row.relative_path).resolve())

        if movies_dir.exists():
            for path in movies_dir.glob(f"{row.id}*"):
                paths_to_delete.add(path.resolve())

        for path in sorted(paths_to_delete):
            try:
                path.relative_to(movies_dir)
            except ValueError:
                continue

            if path.exists() and path.is_file():
                path.unlink()
                deleted_files.append(str(path))

        row.file_name = None
        row.relative_path = None
        row.file_size = None

    db.commit()

    return {
        "status": "deleted",
        "candidate_id": candidate_id,
        "user_id": current_user_id,
        "deleted_files": deleted_files,
        "kept_for_other_users": other_completed_count > 0,
    }
