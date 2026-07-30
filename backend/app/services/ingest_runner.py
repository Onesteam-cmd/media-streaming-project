from datetime import datetime

import httpx

from app.adapters.registry import get_adapter_by_name
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.tables import IngestJobTable, MediaCandidateTable, MediaRequestTable
from app.services.jellyfin_client import JellyfinClient
from app.services.mappers import candidate_table_to_schema
from app.services.prepare_result import PrepareResult, normalize_prepare_result
from app.services.web_media_compat import ensure_web_compatible_prepare_result


def _try_refresh_jellyfin_library() -> str | None:
    settings = get_settings()

    if not settings.jellyfin_api_key:
        return "Jellyfin scan пропущен: JELLYFIN_API_KEY не настроен."

    try:
        client = JellyfinClient()
        client.refresh_library()
        return None

    except httpx.HTTPStatusError as exc:
        return f"Jellyfin scan не выполнен: HTTP {exc.response.status_code}"

    except httpx.RequestError as exc:
        return f"Jellyfin scan не выполнен: {exc}"

    except Exception as exc:
        return f"Jellyfin scan не выполнен: {exc}"


def _apply_prepare_result(
    db,
    job: IngestJobTable,
    request: MediaRequestTable,
    candidate_row: MediaCandidateTable,
    result: PrepareResult,
) -> None:
    status = result.status.value

    if result.external_id:
        job.external_id = result.external_id

    if status == "completed":
        if result.file_name:
            candidate_row.file_name = result.file_name

        if result.relative_path:
            candidate_row.relative_path = result.relative_path

        if result.download_url:
            candidate_row.download_url = result.download_url

        if result.file_size is not None:
            candidate_row.file_size = result.file_size

        job.status = "scanning"
        job.progress = 95
        job.updated_at = datetime.utcnow()

        request.status = "scanning"
        request.updated_at = datetime.utcnow()

        db.commit()

        scan_warning = _try_refresh_jellyfin_library()

        if scan_warning:
            print(scan_warning)

    job.status = status
    job.progress = result.progress
    job.output_path = result.output_path
    job.error_message = result.error_message
    job.updated_at = datetime.utcnow()

    request.status = status
    request.error_message = result.error_message
    request.updated_at = datetime.utcnow()

    db.commit()


def run_ingest_job(job_id: str) -> None:
    db = SessionLocal()

    try:
        job = db.get(IngestJobTable, job_id)

        if job is None:
            return

        request = db.get(MediaRequestTable, job.request_id)
        candidate_row = db.get(MediaCandidateTable, job.candidate_id)

        if request is None or candidate_row is None:
            job.status = "failed"
            job.progress = 0
            job.error_message = "Заявка или кандидат не найдены."
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        adapter = get_adapter_by_name(job.adapter_name)
        candidate = candidate_table_to_schema(candidate_row)

        is_existing_torrent_check = bool(job.external_id and hasattr(adapter, "resume"))

        if is_existing_torrent_check:
            if job.status in {"created", "queued", "running"}:
                job.status = "downloading"
                job.progress = max(job.progress, 5)

                request.status = "downloading"

            job.updated_at = datetime.utcnow()
            request.updated_at = datetime.utcnow()
            db.commit()

            raw_result = adapter.resume(candidate, job.external_id)
        else:
            job.status = "running"
            job.progress = max(job.progress, 10)
            job.updated_at = datetime.utcnow()

            request.status = "running"
            request.updated_at = datetime.utcnow()

            db.commit()

            raw_result = adapter.prepare(candidate)

        result = normalize_prepare_result(raw_result)

        if result.status.value == "completed":
            job.status = "importing"
            job.progress = max(job.progress, 90)
            job.updated_at = datetime.utcnow()

            request.status = "importing"
            request.updated_at = datetime.utcnow()

            db.commit()

        result = ensure_web_compatible_prepare_result(
            result,
            expected_size=candidate_row.file_size,
        )

        _apply_prepare_result(
            db=db,
            job=job,
            request=request,
            candidate_row=candidate_row,
            result=result,
        )

    except Exception as exc:
        job = db.get(IngestJobTable, job_id)

        if job is not None:
            job.status = "failed"
            job.progress = 0
            job.error_message = str(exc)
            job.updated_at = datetime.utcnow()

            request = db.get(MediaRequestTable, job.request_id)
            if request is not None:
                request.status = "failed"
                request.error_message = str(exc)
                request.updated_at = datetime.utcnow()

            db.commit()

    finally:
        db.close()
