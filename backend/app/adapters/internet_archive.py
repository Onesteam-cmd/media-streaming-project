import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.base import IngestAdapter
from app.core.config import get_settings
from app.models.enums import LicenseMode, MediaType
from app.models.schemas import MediaCandidate
from app.services.downloads import DownloadService


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}


class InternetArchiveAdapter(IngestAdapter):
    name = "internet_archive"
    title = "Internet Archive"
    description = "Ищет видеоматериалы через Internet Archive Advanced Search API и скачивает выбранный файл в media/movies."

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.internet_archive_base_url.rstrip("/")
        self.download_service = DownloadService()

    def search(self, query: str) -> list[MediaCandidate]:
        normalized_query = query.strip()

        if not normalized_query:
            return []

        docs = self._search_docs(f'title:("{normalized_query}") AND mediatype:(movies)')

        if not docs:
            words = self._query_words(normalized_query)
            if not words:
                return []

            and_query = " AND ".join(words)
            docs = self._search_docs(f"({and_query}) AND mediatype:(movies)")

        result: list[MediaCandidate] = []

        for doc in docs:
            candidate = self._doc_to_candidate(doc)

            if candidate is not None:
                result.append(candidate)

        return result

    def prepare(self, candidate: MediaCandidate) -> dict:
        if not candidate.item_identifier:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "У кандидата Internet Archive не указан item_identifier.",
            }

        selected_file = self._select_best_video_file(candidate.item_identifier)

        if selected_file is None:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "Не найден подходящий видеофайл в пределах лимита размера.",
            }

        file_name = selected_file["name"]
        file_size = selected_file.get("size")

        download_url = self._build_download_url(candidate.item_identifier, file_name)
        output_path = self._build_output_path(candidate.item_identifier, file_name)

        try:
            self.download_service.download_file(download_url, output_path)
        except Exception as exc:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": f"Ошибка скачивания: {exc}",
            }

        return {
            "status": "completed",
            "progress": 100,
            "output_path": str(output_path),
            "error_message": None,
            "file_name": output_path.name,
            "relative_path": f"movies/{output_path.name}",
            "download_url": download_url,
            "file_size": file_size,
        }

    def status(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "status": "handled_by_backend_job",
        }

    def _search_docs(self, archive_query: str) -> list[dict[str, Any]]:
        params = [
            ("q", archive_query),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("fl[]", "description"),
            ("fl[]", "date"),
            ("fl[]", "year"),
            ("fl[]", "licenseurl"),
            ("fl[]", "rights"),
            ("fl[]", "mediatype"),
            ("sort[]", "downloads desc"),
            ("rows", str(self.settings.internet_archive_search_rows)),
            ("page", "1"),
            ("output", "json"),
        ]

        url = f"{self.base_url}/advancedsearch.php"

        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        docs = data.get("response", {}).get("docs", [])

        if not isinstance(docs, list):
            return []

        return docs

    def _select_best_video_file(self, identifier: str) -> dict[str, Any] | None:
        metadata = self._get_metadata(identifier)
        files = metadata.get("files", [])

        if not isinstance(files, list):
            return None

        candidates: list[dict[str, Any]] = []

        for file_item in files:
            if not isinstance(file_item, dict):
                continue

            name = self._clean_text(file_item.get("name"))
            extension = Path(name).suffix.lower()

            if extension not in VIDEO_EXTENSIONS:
                continue

            if self._is_derivative_metadata_file(name):
                continue

            size = self._parse_size(file_item.get("size"))

            if size is None:
                continue

            if size > self._max_file_size_bytes():
                continue

            candidates.append(
                {
                    "name": name,
                    "size": size,
                    "format": self._clean_text(file_item.get("format")),
                }
            )

        if not candidates:
            return None

        candidates.sort(key=lambda item: self._score_file(item), reverse=True)

        return candidates[0]

    def _get_metadata(self, identifier: str) -> dict[str, Any]:
        safe_identifier = quote(identifier, safe="")
        url = f"{self.base_url}/metadata/{safe_identifier}"

        with httpx.Client(timeout=20.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            return {}

        return data

    def _build_download_url(self, identifier: str, file_name: str) -> str:
        safe_identifier = quote(identifier, safe="")
        safe_file_name = quote(file_name, safe="/")

        return f"{self.base_url}/download/{safe_identifier}/{safe_file_name}"

    def _build_output_path(self, identifier: str, file_name: str) -> Path:
        movies_dir = Path(self.settings.movies_dir)

        safe_identifier = self._safe_filename(identifier)
        safe_file_name = self._safe_filename(Path(file_name).name)

        return movies_dir / f"{safe_identifier}__{safe_file_name}"

    def _doc_to_candidate(self, doc: dict[str, Any]) -> MediaCandidate | None:
        identifier = self._clean_text(doc.get("identifier"))

        if not identifier:
            return None

        title = self._clean_text(doc.get("title")) or identifier
        description = self._clean_text(doc.get("description"))
        year = self._extract_year(doc)

        return MediaCandidate(
            id=f"internet-archive-{identifier}",
            title=title,
            original_title=title,
            year=year,
            media_type=MediaType.movie,
            description=description,
            source=self.name,
            license_mode=self._detect_license_mode(doc),
            file_name=None,
            relative_path=None,
            item_identifier=identifier,
            download_url=None,
            file_size=None,
        )

    def _extract_year(self, doc: dict[str, Any]) -> int | None:
        direct_year = self._clean_text(doc.get("year"))

        if direct_year and direct_year.isdigit():
            return int(direct_year)

        date_value = self._clean_text(doc.get("date"))

        if not date_value:
            return None

        match = re.search(r"\b(18|19|20)\d{2}\b", date_value)

        if not match:
            return None

        return int(match.group(0))

    def _detect_license_mode(self, doc: dict[str, Any]) -> LicenseMode:
        license_url = self._clean_text(doc.get("licenseurl")).lower()
        rights = self._clean_text(doc.get("rights")).lower()
        description = self._clean_text(doc.get("description")).lower()

        if "public domain" in rights or "public-domain" in rights:
            return LicenseMode.public_domain

        if "public domain" in description:
            return LicenseMode.public_domain

        if "creativecommons.org" in license_url:
            return LicenseMode.creative_commons

        return LicenseMode.unknown

    def _score_file(self, file_item: dict[str, Any]) -> int:
        name = file_item["name"].lower()
        extension = Path(name).suffix.lower()
        size = int(file_item.get("size") or 0)

        score = 0

        if extension == ".mp4":
            score += 50
        elif extension in {".m4v", ".webm", ".ogv"}:
            score += 30
        else:
            score += 10

        if "512kb" in name:
            score += 30

        if "h.264" in name or "h264" in name:
            score += 20

        if "720" in name:
            score += 10

        if "1080" in name:
            score -= 20

        if "trailer" in name:
            score -= 5

        score -= size // (1024 * 1024 * 100)

        return score

    def _parse_size(self, value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except ValueError:
            return None
        except TypeError:
            return None

    def _max_file_size_bytes(self) -> int:
        return self.settings.internet_archive_max_file_size_mb * 1024 * 1024

    def _is_derivative_metadata_file(self, name: str) -> bool:
        lowered = name.lower()

        blocked_parts = [
            "_files.xml",
            "_meta.xml",
            "_reviews.xml",
            "_archive.torrent",
            "_thumb",
            ".gif",
            ".jpg",
            ".jpeg",
            ".png",
            ".txt",
            ".xml",
            ".json",
            ".sqlite",
        ]

        return any(part in lowered for part in blocked_parts)

    def _query_words(self, query: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9]+", query.lower())

        return [word for word in words if len(word) >= 2]

    def _safe_filename(self, value: str) -> str:
        value = value.strip()
        value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
        value = value.strip("._")

        return value or "downloaded_file"

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, list):
            value = " ".join(str(item) for item in value if item is not None)

        text = str(value)
        text = re.sub(r"\s+", " ", text).strip()

        return text
