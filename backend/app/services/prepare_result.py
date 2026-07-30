from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.models.enums import IngestStatus


class PrepareResult(BaseModel):
    status: IngestStatus
    progress: int = Field(default=0, ge=0, le=100)
    output_path: str | None = None
    error_message: str | None = None

    file_name: str | None = None
    relative_path: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    external_id: str | None = None


def normalize_prepare_result(raw_result: Any) -> PrepareResult:
    if not isinstance(raw_result, dict):
        return PrepareResult(
            status=IngestStatus.failed,
            progress=0,
            error_message="Адаптер вернул prepare result не в формате dict.",
        )

    try:
        return PrepareResult.model_validate(raw_result)

    except ValidationError as exc:
        return PrepareResult(
            status=IngestStatus.failed,
            progress=0,
            error_message=f"Некорректный prepare result: {exc}",
        )
