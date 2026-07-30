import json
import re
import time
from pathlib import Path

from app.adapters.base import IngestAdapter
from app.core.config import get_settings
from app.models.schemas import MediaCandidate
from app.services.media_import import MediaImportService
from app.services.transmission_client import TransmissionClient
from app.services.torrent_ingest import TorrentIngestService


class TorrentDemoAdapter(IngestAdapter):
    name = "torrent_demo"
    title = "Torrent demo"
    description = "Учебный torrent-compatible adapter. Читает локальный каталог, добавляет torrent/magnet в Transmission и импортирует видео в media/movies."

    def __init__(self) -> None:
        self.settings = get_settings()
        self.catalog_path = Path("/app/catalogs/torrent_demo_catalog.json")
        self.transmission = TransmissionClient()
        self.media_import = MediaImportService()
        self.torrent_ingest = TorrentIngestService()

    def search(self, query: str) -> list[MediaCandidate]:
        items = self._load_catalog()
        query_words = self._query_words(query)

        if not query_words:
            return items

        result: list[MediaCandidate] = []

        for item in items:
            searchable_text = " ".join(
                [
                    item.id or "",
                    item.title or "",
                    item.original_title or "",
                    str(item.year or ""),
                    item.description or "",
                    item.item_identifier or "",
                    item.download_url or "",
                    item.source or "",
                ]
            ).lower()

            if all(word in searchable_text for word in query_words):
                result.append(item)

        return result

    def prepare(self, candidate: MediaCandidate) -> dict:
        if not candidate.download_url:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "У torrent_demo candidate не указан download_url.",
            }

        torrent_id = self.torrent_ingest.add_torrent(candidate.download_url)

        return self.torrent_ingest.check_and_import(
            torrent_id=torrent_id,
            candidate=candidate,
        )

    def resume(self, candidate: MediaCandidate, external_id: str) -> dict:
        return self.torrent_ingest.check_and_import(
            torrent_id=int(external_id),
            candidate=candidate,
        )

    def status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "status": "handled_by_transmission",
        }

    def _wait_for_torrent(self, torrent_id: int) -> dict | None:
        for _ in range(20):
            torrent = self.transmission.torrent_get_by_id(torrent_id)

            if torrent is None:
                return None

            if torrent.get("error"):
                raise RuntimeError(torrent.get("errorString") or "Transmission torrent error")

            percent_done = float(torrent.get("percentDone") or 0)

            if percent_done >= 1.0:
                return torrent

            time.sleep(3)

        return None

    def _find_downloaded_video_file(self, torrent: dict) -> Path | None:
        download_dir = torrent.get("downloadDir") or "/downloads/complete"
        backend_download_root = Path(self.settings.transmission_backend_downloads_dir)

        relative_download_dir = download_dir.removeprefix("/downloads").strip("/")
        backend_download_dir = backend_download_root / relative_download_dir

        files = torrent.get("files") or []
        video_candidates: list[Path] = []

        for file_item in files:
            name = file_item.get("name")

            if not name:
                continue

            direct_path = backend_download_dir / name

            if (
                direct_path.exists()
                and direct_path.is_file()
                and direct_path.suffix.lower() in {".mp4", ".m4v", ".webm", ".ogv", ".avi", ".mov", ".mkv"}
            ):
                video_candidates.append(direct_path)

        if video_candidates:
            video_candidates.sort(
                key=lambda path: path.stat().st_size,
                reverse=True,
            )
            return video_candidates[0]

        found = self.media_import.find_first_video_file(backend_download_dir)

        if found is not None:
            return found

        return self.media_import.find_first_video_file(backend_download_root)

    def _load_catalog(self) -> list[MediaCandidate]:
        if not self.catalog_path.exists():
            return []

        with self.catalog_path.open("r", encoding="utf-8") as file:
            raw_items = json.load(file)

        return [MediaCandidate.model_validate(item) for item in raw_items]

    def _query_words(self, query: str) -> list[str]:
        return [
            word
            for word in re.findall(r"[a-zA-Z0-9]+", query.lower())
            if len(word) >= 2
        ]
