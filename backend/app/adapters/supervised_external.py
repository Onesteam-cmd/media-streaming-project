from app.adapters.base import IngestAdapter
from app.models.schemas import MediaCandidate


class SupervisedExternalAdapter(IngestAdapter):
    name = "supervised_external"
    title = "Supervised external"
    description = "Заглушка для учебного внешнего источника. В первом этапе отключена."

    def search(self, query: str) -> list[MediaCandidate]:
        return []

    def prepare(self, candidate: MediaCandidate) -> dict:
        return {
            "status": "failed",
            "progress": 0,
            "output_path": None,
            "error_message": "supervised_external отключён в первом этапе.",
        }

    def status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "status": "disabled",
        }
