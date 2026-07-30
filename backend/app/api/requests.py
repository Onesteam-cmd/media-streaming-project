from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import func, select
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.schemas import MediaRequestCreate, MediaRequestDetail
from app.models.tables import IngestJobTable, MediaCandidateTable, MediaRequestTable
from app.services.ingest_runner import run_ingest_job
from app.services.mappers import candidate_table_to_summary, job_table_to_schema, request_table_to_schema
from app.services.transmission_client import TransmissionClient
from app.services.user_context import get_current_user_id


router = APIRouter(prefix="/api/requests", tags=["requests"], dependencies=[Depends(get_current_user_id)])

ACTIVE_REQUEST_STATUSES = {
    "created",
    "queued",
    "running",
    "downloading",
    "importing",
    "scanning",
}

RECOVERABLE_REQUEST_STATUSES = ACTIVE_REQUEST_STATUSES | {
    "completed",
}


def _candidate_title_key(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())



VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}


def _candidate_media_prefix(candidate_id: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in candidate_id
    )

    return safe



def _candidate_expected_min_size(candidate: MediaCandidateTable | None) -> int:
    if candidate is None or not candidate.file_size:
        return 1

    return int(candidate.file_size * 0.9)


def _candidate_has_available_media(candidate: MediaCandidateTable | None) -> bool:
    if candidate is None or not candidate.relative_path:
        return False

    settings = get_settings()
    media_root = Path(settings.media_root).resolve()
    file_path = (media_root / candidate.relative_path).resolve()

    try:
        file_path.relative_to(media_root)
    except ValueError:
        return False

    return file_path.exists() and file_path.is_file() and file_path.stat().st_size > 0


def _find_existing_media_file(candidate: MediaCandidateTable) -> Path | None:
    settings = get_settings()
    movies_dir = Path(settings.movies_dir).resolve()
    prefix = _candidate_media_prefix(candidate.id)
    min_size = _candidate_expected_min_size(candidate)

    if not movies_dir.exists():
        return None

    candidates: list[Path] = []

    for file_path in movies_dir.glob(f"{prefix}*"):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        if ".tmp" in file_path.name.lower():
            continue

        if file_path.stat().st_size < min_size:
            continue

        candidates.append(file_path)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item.stat().st_size, reverse=True)

    return candidates[0]


def _complete_request_from_existing_media(
    db: Session,
    media_request: MediaRequestTable,
    job: IngestJobTable,
    candidate: MediaCandidateTable,
    file_path: Path,
) -> None:
    settings = get_settings()
    media_root = Path(settings.media_root).resolve()
    relative_path = file_path.resolve().relative_to(media_root).as_posix()

    candidate.file_name = file_path.name
    candidate.relative_path = relative_path
    candidate.file_size = file_path.stat().st_size

    job.status = "completed"
    job.progress = 100
    job.output_path = str(file_path)
    job.error_message = None
    job.updated_at = datetime.utcnow()

    media_request.status = "completed"
    media_request.error_message = None
    media_request.updated_at = datetime.utcnow()

    db.commit()


def _try_recover_request_from_existing_media(
    db: Session,
    media_request: MediaRequestTable,
) -> None:
    if media_request.status not in RECOVERABLE_REQUEST_STATUSES:
        return

    candidate = db.get(MediaCandidateTable, media_request.candidate_id)

    if candidate is None:
        return

    if _candidate_has_available_media(candidate):
        return

    job = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.request_id == media_request.id)
        .order_by(IngestJobTable.created_at.desc())
    ).first()

    if job is None:
        return

    if job.status not in RECOVERABLE_REQUEST_STATUSES:
        return

    file_path = _find_existing_media_file(candidate)

    if file_path is None:
        return

    _complete_request_from_existing_media(
        db=db,
        media_request=media_request,
        job=job,
        candidate=candidate,
        file_path=file_path,
    )


def _job_table_to_schema_with_live_torrent(job: IngestJobTable | None):
    if job is None:
        return None

    schema = job_table_to_schema(job)

    if not job.external_id:
        return schema

    try:
        torrent_id = int(job.external_id)
    except ValueError:
        return schema

    try:
        torrent = TransmissionClient().torrent_get_by_id(torrent_id)
    except Exception as exc:
        print(f"Transmission live stats skipped: {exc}")
        return schema

    if torrent is None:
        return schema

    rate_download = torrent.get("rateDownload")
    eta = torrent.get("eta")
    peers_connected = torrent.get("peersConnected")

    update = {}

    if isinstance(rate_download, (int, float)) and rate_download >= 0:
        update["download_speed_kbps"] = round(float(rate_download) / 1024, 1)

    if isinstance(eta, int) and eta >= 0:
        update["eta_seconds"] = eta

    if isinstance(peers_connected, int):
        update["peers_connected"] = peers_connected

    if not update:
        return schema

    return schema.model_copy(update=update)


def _request_detail(
    db: Session,
    media_request: MediaRequestTable,
    fallback_candidate: MediaCandidateTable | None = None,
) -> MediaRequestDetail:
    _try_recover_request_from_existing_media(db, media_request)

    job = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.request_id == media_request.id)
        .order_by(IngestJobTable.created_at.desc())
    ).first()

    candidate = db.get(MediaCandidateTable, media_request.candidate_id) or fallback_candidate

    return MediaRequestDetail(
        request=request_table_to_schema(media_request),
        job=_job_table_to_schema_with_live_torrent(job),
        candidate=(
            candidate_table_to_summary(candidate)
            if candidate is not None
            else None
        ),
    )



def _candidate_has_available_media(candidate: MediaCandidateTable | None) -> bool:
    if candidate is None or not candidate.relative_path:
        return False

    settings = get_settings()
    media_root = Path(settings.media_root).resolve()
    file_path = (media_root / candidate.relative_path).resolve()

    try:
        file_path.relative_to(media_root)
    except ValueError:
        return False

    return file_path.exists() and file_path.is_file() and file_path.stat().st_size > 0


def _request_detail(
    db: Session,
    media_request: MediaRequestTable,
    fallback_candidate: MediaCandidateTable | None = None,
) -> MediaRequestDetail:
    job = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.request_id == media_request.id)
        .order_by(IngestJobTable.created_at.desc())
    ).first()

    candidate = db.get(MediaCandidateTable, media_request.candidate_id) or fallback_candidate

    return MediaRequestDetail(
        request=request_table_to_schema(media_request),
        job=_job_table_to_schema_with_live_torrent(job),
        candidate=(
            candidate_table_to_summary(candidate)
            if candidate is not None
            else None
        ),
    )




@router.get("")
def list_requests(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    if limit < 1:
        limit = 1

    if limit > 100:
        limit = 100

    if offset < 0:
        offset = 0

    count_query = (
        select(func.count())
        .select_from(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
    )
    items_query = (
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .order_by(MediaRequestTable.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if status:
        count_query = count_query.where(MediaRequestTable.status == status)
        items_query = items_query.where(MediaRequestTable.status == status)

    total = db.scalar(count_query) or 0
    rows = db.scalars(items_query).all()

    items = []

    for row in rows:
        items.append(_request_detail(db, row))

    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.post("", response_model=MediaRequestDetail)
def create_request(
    payload: MediaRequestCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MediaRequestDetail:
    candidate = db.get(MediaCandidateTable, payload.candidate_id)

    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail="Кандидат не найден. Сначала вызови POST /api/search.",
        )

    existing_request = db.scalars(
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .where(MediaRequestTable.candidate_id == payload.candidate_id)
        .where(MediaRequestTable.status.in_(ACTIVE_REQUEST_STATUSES))
        .order_by(MediaRequestTable.created_at.desc())
    ).first()

    if existing_request is None:
        target_title_key = _candidate_title_key(candidate.title)

        possible_existing_requests = db.scalars(
            select(MediaRequestTable)
            .where(MediaRequestTable.user_id == current_user_id)
            .where(MediaRequestTable.status.in_(ACTIVE_REQUEST_STATUSES))
            .order_by(MediaRequestTable.created_at.desc())
            .limit(100)
        ).all()

        for possible_request in possible_existing_requests:
            possible_candidate = db.get(MediaCandidateTable, possible_request.candidate_id)

            if possible_candidate is None:
                continue

            if _candidate_title_key(possible_candidate.title) == target_title_key:
                existing_request = possible_request
                break

    if existing_request is not None:
        return _request_detail(db, existing_request, candidate)

    reusable_completed_request = db.scalars(
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .where(MediaRequestTable.candidate_id == payload.candidate_id)
        .where(MediaRequestTable.status == "completed")
        .order_by(MediaRequestTable.created_at.desc())
    ).first()

    if reusable_completed_request is not None:
        reusable_candidate = db.get(MediaCandidateTable, reusable_completed_request.candidate_id)

        if _candidate_has_available_media(reusable_candidate):
            return _request_detail(db, reusable_completed_request, candidate)

    target_title_key = _candidate_title_key(candidate.title)
    possible_completed_requests = db.scalars(
        select(MediaRequestTable)
        .where(MediaRequestTable.user_id == current_user_id)
        .where(MediaRequestTable.status == "completed")
        .order_by(MediaRequestTable.created_at.desc())
        .limit(100)
    ).all()

    for possible_request in possible_completed_requests:
        possible_candidate = db.get(MediaCandidateTable, possible_request.candidate_id)

        if possible_candidate is None:
            continue

        if _candidate_title_key(possible_candidate.title) != target_title_key:
            continue

        if _candidate_has_available_media(possible_candidate):
            return _request_detail(db, possible_request, candidate)


    media_request = MediaRequestTable(
        user_id=current_user_id,
        candidate_id=payload.candidate_id,
        status="queued",
    )

    db.add(media_request)
    db.flush()

    job = IngestJobTable(
        request_id=media_request.id,
        adapter_name=candidate.source,
        candidate_id=payload.candidate_id,
        status="queued",
        progress=0,
    )

    db.add(job)
    db.commit()

    db.refresh(media_request)
    db.refresh(job)

    background_tasks.add_task(run_ingest_job, job.id)

    return MediaRequestDetail(
        request=request_table_to_schema(media_request),
        job=job_table_to_schema(job),
        candidate=candidate_table_to_summary(candidate),
    )



@router.post("/refresh-active")
def refresh_downloading_requests(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    stale_cutoff = datetime.utcnow() - timedelta(minutes=60)

    active_jobs = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.status.in_(ACTIVE_REQUEST_STATUSES))
        .order_by(IngestJobTable.updated_at.asc())
        .limit(100)
    ).all()

    jobs = []

    for job in active_jobs:
        if job.status in {"created", "queued", "downloading"}:
            jobs.append(job)
            continue

        if job.updated_at is None or job.updated_at <= stale_cutoff:
            jobs.append(job)

    jobs = jobs[:20]

    for job in jobs:
        background_tasks.add_task(run_ingest_job, job.id)

    return {
        "scheduled": len(jobs),
        "job_ids": [job.id for job in jobs],
    }



@router.post("/{request_id}/refresh", response_model=MediaRequestDetail)
def refresh_request(
    request_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MediaRequestDetail:
    media_request = db.get(MediaRequestTable, request_id)

    if media_request is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    if media_request.user_id != current_user_id:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    job = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.request_id == request_id)
        .order_by(IngestJobTable.created_at.desc())
    ).first()

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job для заявки не найден.",
        )

    if job.status in {"created", "queued", "downloading"}:
        background_tasks.add_task(run_ingest_job, job.id)
    elif job.status in {"running", "importing", "scanning"}:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=60)

        if job.updated_at is None or job.updated_at <= stale_cutoff:
            background_tasks.add_task(run_ingest_job, job.id)

    candidate = db.get(MediaCandidateTable, media_request.candidate_id)

    return MediaRequestDetail(
        request=request_table_to_schema(media_request),
        job=job_table_to_schema(job),
        candidate=(
            candidate_table_to_summary(candidate)
            if candidate is not None
            else None
        ),
    )



@router.post("/{request_id}/cancel", response_model=MediaRequestDetail)
def cancel_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MediaRequestDetail:
    media_request = db.get(MediaRequestTable, request_id)

    if media_request is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    if media_request.user_id != current_user_id:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    job = db.scalars(
        select(IngestJobTable)
        .where(IngestJobTable.request_id == request_id)
        .order_by(IngestJobTable.created_at.desc())
    ).first()

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job для заявки не найден.",
        )

    if job.external_id:
        try:
            TransmissionClient().torrent_remove(
                torrent_id=int(job.external_id),
                delete_local_data=True,
            )
        except Exception as exc:
            print(f"Transmission remove skipped: {exc}")

    job.status = "cancelled"
    job.progress = 0
    job.error_message = "Загрузка отменена пользователем."
    job.updated_at = datetime.utcnow()

    media_request.status = "cancelled"
    media_request.error_message = "Загрузка отменена пользователем."
    media_request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(media_request)
    db.refresh(job)

    candidate = db.get(MediaCandidateTable, media_request.candidate_id)

    return MediaRequestDetail(
        request=request_table_to_schema(media_request),
        job=job_table_to_schema(job),
        candidate=(
            candidate_table_to_summary(candidate)
            if candidate is not None
            else None
        ),
    )


@router.get("/{request_id}", response_model=MediaRequestDetail)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MediaRequestDetail:
    media_request = db.get(MediaRequestTable, request_id)

    if media_request is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    if media_request.user_id != current_user_id:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    return _request_detail(db, media_request)
