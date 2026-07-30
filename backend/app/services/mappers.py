from app.models.enums import IngestStatus, LicenseMode, MediaType, RequestStatus
from app.models.schemas import IngestJobRead, MediaCandidate, MediaCandidateSummary, MediaRequestRead
from app.models.tables import IngestJobTable, MediaCandidateTable, MediaRequestTable


def candidate_table_to_schema(row: MediaCandidateTable) -> MediaCandidate:
    return MediaCandidate(
        id=row.id,
        title=row.title,
        original_title=row.original_title,
        year=row.year,
        media_type=MediaType(row.media_type),
        description=row.description,
        source=row.source,
        license_mode=LicenseMode(row.license_mode),
        file_name=row.file_name,
        relative_path=row.relative_path,
        item_identifier=row.item_identifier,
        download_url=row.download_url,
        file_size=row.file_size,
        quality_label=row.quality_label,
        audio_label=row.audio_label,
        rank_score=row.rank_score,
        size_gb=round(row.file_size / (1024 ** 3), 2) if row.file_size else None,
    )


def candidate_schema_to_table(candidate: MediaCandidate) -> MediaCandidateTable:
    return MediaCandidateTable(
        id=candidate.id,
        title=candidate.title,
        original_title=candidate.original_title,
        year=candidate.year,
        media_type=candidate.media_type.value,
        description=candidate.description,
        source=candidate.source,
        license_mode=candidate.license_mode.value,
        file_name=candidate.file_name,
        relative_path=candidate.relative_path,
        item_identifier=candidate.item_identifier,
        download_url=candidate.download_url,
        file_size=candidate.file_size,
    )


def candidate_table_to_summary(row: MediaCandidateTable) -> MediaCandidateSummary:
    return MediaCandidateSummary(
        id=row.id,
        title=row.title,
        source=row.source,
        year=row.year,
        file_name=row.file_name,
        relative_path=row.relative_path,
    )


def update_candidate_table(row: MediaCandidateTable, candidate: MediaCandidate) -> None:
    row.title = candidate.title
    row.original_title = candidate.original_title
    row.year = candidate.year
    row.media_type = candidate.media_type.value
    row.description = candidate.description
    row.source = candidate.source
    row.license_mode = candidate.license_mode.value
    row.file_name = candidate.file_name
    row.relative_path = candidate.relative_path
    row.item_identifier = candidate.item_identifier
    row.download_url = candidate.download_url
    row.file_size = candidate.file_size


def request_table_to_schema(row: MediaRequestTable) -> MediaRequestRead:
    return MediaRequestRead(
        id=row.id,
        user_id=row.user_id,
        candidate_id=row.candidate_id,
        status=RequestStatus(row.status),
        error_message=row.error_message,
    )


def job_table_to_schema(row: IngestJobTable) -> IngestJobRead:
    return IngestJobRead(
        id=row.id,
        request_id=row.request_id,
        adapter_name=row.adapter_name,
        candidate_id=row.candidate_id,
        status=IngestStatus(row.status),
        progress=row.progress,
        output_path=row.output_path,
        error_message=row.error_message,
        external_id=row.external_id,
    )
