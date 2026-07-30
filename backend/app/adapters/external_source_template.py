from app.adapters.base import IngestAdapter
from app.models.enums import LicenseMode, MediaType
from app.models.schemas import MediaCandidate


class ExternalSourceTemplateAdapter(IngestAdapter):
    name = "external_source_template"
    title = "External source template"
    description = "Шаблон адаптера для подключения внешнего поставщика без изменения основного backend."

    def search(self, query: str) -> list[MediaCandidate]:
        normalized_query = query.strip()

        if not normalized_query:
            return []

        return [
            MediaCandidate(
                id="external-template-example",
                title=f"Example result for: {normalized_query}",
                original_title=f"Example result for: {normalized_query}",
                year=None,
                media_type=MediaType.movie,
                description=(
                    "Это шаблонный результат. "
                    "В реальном адаптере здесь должен быть результат поиска внешнего источника."
                ),
                source=self.name,
                license_mode=LicenseMode.unknown,
                file_name=None,
                relative_path=None,
                item_identifier="external-template-example",
                download_url=None,
                file_size=None,
            )
        ]

    def prepare(self, candidate: MediaCandidate) -> dict:
        return {
            "status": "failed",
            "progress": 0,
            "output_path": None,
            "error_message": (
                "ExternalSourceTemplateAdapter не скачивает файлы. "
                "Скопируй этот adapter и реализуй search() и prepare() под конкретный источник."
            ),
        }

    def status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "status": "template",
        }
