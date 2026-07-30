import json
from pathlib import Path

from app.adapters.base import IngestAdapter
from app.core.config import get_settings
from app.models.schemas import MediaCandidate


class LocalDemoAdapter(IngestAdapter):
    name = "local_demo"
    title = "Local demo"
    description = "Ищет записи в локальном JSON-каталоге и проверяет наличие файла в media/movies."

    def __init__(self) -> None:
        self.settings = get_settings()

    def _load_catalog(self) -> list[MediaCandidate]:
        catalog_path = Path(self.settings.local_catalog_path)

        if not catalog_path.exists():
            return []

        with catalog_path.open("r", encoding="utf-8") as file:
            raw_items = json.load(file)

        return [MediaCandidate.model_validate(item) for item in raw_items]

    def search(self, query: str) -> list[MediaCandidate]:
        items = self._load_catalog()
        normalized_query = query.strip().lower()

        if not normalized_query:
            return items

        result: list[MediaCandidate] = []

        for item in items:
            searchable_text = " ".join(
                [
                    item.title or "",
                    item.original_title or "",
                    str(item.year or ""),
                    item.description or "",
                    item.file_name or "",
                ]
            ).lower()

            if normalized_query in searchable_text:
                result.append(item)

        return result

    def prepare(self, candidate: MediaCandidate) -> dict:
        if not candidate.relative_path:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "У кандидата не указан relative_path.",
            }

        media_root = Path(self.settings.media_root)
        expected_path = media_root / candidate.relative_path

        if expected_path.exists() and expected_path.is_file():
            return {
                "status": "completed",
                "progress": 100,
                "output_path": str(expected_path),
                "error_message": None,
            }

        return {
            "status": "failed",
            "progress": 0,
            "output_path": None,
            "error_message": f"Файл не найден: {expected_path}",
        }

    def status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "status": "unknown",
        }
