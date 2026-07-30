import base64
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.models.schemas import MediaCandidate
from app.services.media_import import MediaImportService
from app.services.transmission_client import TransmissionClient


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}


REDIRECT_STATUS_CODES = {
    301,
    302,
    303,
    307,
    308,
}


class TorrentIngestService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.transmission = TransmissionClient()
        self.media_import = MediaImportService()

    def add_torrent(self, download_url: str) -> int:
        add_arguments = self._build_torrent_add_arguments(download_url)

        torrent = self.transmission.torrent_add(
            filename=add_arguments.get("filename"),
            metainfo=add_arguments.get("metainfo"),
            download_dir="/downloads/complete",
        )

        torrent_id = torrent.get("id")

        if torrent_id is None:
            raise RuntimeError("Transmission не вернул torrent id.")

        return int(torrent_id)

    def check_and_import(self, torrent_id: int, candidate: MediaCandidate) -> dict:
        torrent = self.transmission.torrent_get_by_id(torrent_id)

        if torrent is None:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": f"Torrent не найден в Transmission: {torrent_id}",
                "external_id": str(torrent_id),
            }

        if torrent.get("error"):
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": torrent.get("errorString") or "Transmission torrent error",
                "external_id": str(torrent_id),
            }

        percent_done = float(torrent.get("percentDone") or 0)

        if percent_done < 1.0:
            progress = max(5, min(94, int(percent_done * 90)))

            return {
                "status": "downloading",
                "progress": progress,
                "output_path": None,
                "error_message": None,
                "external_id": str(torrent_id),
            }

        source_file = self._find_downloaded_video_file(torrent)

        if source_file is None:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "Torrent завершён, но видеофайл не найден в downloads.",
                "external_id": str(torrent_id),
            }

        return {
            "status": "completed",
            "progress": 100,
            "output_path": str(source_file),
            "error_message": None,
            "file_name": source_file.name,
            "relative_path": None,
            "download_url": candidate.download_url,
            "file_size": source_file.stat().st_size,
            "external_id": str(torrent_id),
        }

    def _build_torrent_add_arguments(self, download_url: str) -> dict[str, str]:
        value = download_url.strip()

        if value.startswith("magnet:"):
            return {
                "filename": value,
            }

        if not value.startswith(("http://", "https://")):
            return {
                "filename": value,
            }

        resolved = self._resolve_http_torrent_source(value)

        if resolved.startswith("magnet:"):
            return {
                "filename": resolved,
            }

        return {
            "metainfo": resolved,
        }

    def _resolve_http_torrent_source(self, url: str) -> str:
        current_url = url

        with httpx.Client(
            timeout=max(30.0, float(self.settings.jackett_timeout_seconds)),
            follow_redirects=False,
            headers={
                "User-Agent": "media-streaming-project/1.0",
                "Accept": "application/x-bittorrent,application/octet-stream,text/plain,*/*",
            },
        ) as client:
            for _ in range(10):
                response = client.get(current_url)

                if response.status_code in REDIRECT_STATUS_CODES:
                    location = response.headers.get("location")

                    if not location:
                        raise RuntimeError(
                            f"Torrent source redirect without Location: HTTP {response.status_code}"
                        )

                    if location.startswith("magnet:"):
                        return location

                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()

                content = response.content

                if not content:
                    raise RuntimeError("Torrent source returned empty response.")

                possible_text = content[:4096].decode("utf-8", errors="ignore").strip()

                if possible_text.startswith("magnet:"):
                    return possible_text.splitlines()[0].strip()

                return base64.b64encode(content).decode("ascii")

        raise RuntimeError("Torrent source had too many redirects.")

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
                and direct_path.suffix.lower() in VIDEO_EXTENSIONS
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
