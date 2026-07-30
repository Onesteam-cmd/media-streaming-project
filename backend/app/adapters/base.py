from abc import ABC, abstractmethod

from app.models.schemas import MediaCandidate


class IngestAdapter(ABC):
    name: str
    title: str
    description: str

    @abstractmethod
    def search(self, query: str) -> list[MediaCandidate]:
        raise NotImplementedError

    @abstractmethod
    def prepare(self, candidate: MediaCandidate) -> dict:
        raise NotImplementedError

    @abstractmethod
    def status(self, job_id: str) -> dict:
        raise NotImplementedError
