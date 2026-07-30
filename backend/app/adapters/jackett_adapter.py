import hashlib
import html
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.base import IngestAdapter
from app.core.config import get_settings
from app.models.enums import LicenseMode, MediaType
from app.models.schemas import MediaCandidate
from app.services.media_import import MediaImportService
from app.services.query_relevance import QueryRelevanceFilter
from app.services.torrent_quality import TorrentQualityRanker
from app.services.transmission_client import TransmissionClient
from app.services.torrent_ingest import TorrentIngestService


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}


class JackettAdapter(IngestAdapter):
    name = "jackett"
    title = "Jackett"
    description = "Поиск через подключённые Jackett indexers и подготовка через Transmission."

    def __init__(self) -> None:
        self.settings = get_settings()
        self.transmission = TransmissionClient()
        self.media_import = MediaImportService()
        self.torrent_ingest = TorrentIngestService()
        self.query_relevance = QueryRelevanceFilter()
        self.quality_ranker = TorrentQualityRanker(
            require_russian_audio=self.settings.jackett_require_russian_audio,
            strict_russian_only=self.settings.jackett_strict_russian_only,
            exclude_bad_quality=self.settings.jackett_exclude_bad_quality,
        )

    def search(self, query: str) -> list[MediaCandidate]:
        normalized_query = query.strip()

        if not normalized_query:
            return []

        if not self.settings.jackett_api_key:
            return []

        endpoint = (
            f"{self.settings.jackett_url.rstrip('/')}"
            "/api/v2.0/indexers/all/results/torznab/api"
        )

        params = {
            "apikey": self.settings.jackett_api_key,
            "t": "search",
            "q": normalized_query,
            "cat": self.settings.jackett_categories,
        }

        with httpx.Client(timeout=self.settings.jackett_timeout_seconds) as client:
            response = client.get(endpoint, params=params)
            response.raise_for_status()

        return self._parse_torznab_xml(response.text, normalized_query)

    def prepare(self, candidate: MediaCandidate) -> dict:
        if not candidate.download_url:
            return {
                "status": "failed",
                "progress": 0,
                "output_path": None,
                "error_message": "У Jackett candidate не указан download_url.",
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

    def _parse_torznab_xml(self, xml_text: str, query: str) -> list[MediaCandidate]:
        root = ET.fromstring(xml_text)

        items = root.findall(".//channel/item")
        best_by_release_key: dict[str, tuple[int, int, MediaCandidate]] = {}

        for item in items:
            title = self._find_text(item, "title") or "Без названия"
            guid = self._find_text(item, "guid") or title
            description = self._clean_description(self._find_text(item, "description"))
            link = self._find_text(item, "link")
            enclosure_url = self._find_enclosure_url(item)
            magnet_url = self._find_torznab_attr(item, "magneturl")
            size = self._parse_int(
                self._find_torznab_attr(item, "size")
                or self._find_enclosure_length(item)
            )
            seeders = self._parse_int(
                self._find_torznab_attr(item, "seeders")
                or self._find_torznab_attr(item, "seeds")
                or self._find_torznab_attr(item, "seed")
            )
            peers = self._parse_int(
                self._find_torznab_attr(item, "peers")
                or self._find_torznab_attr(item, "leechers")
                or self._find_torznab_attr(item, "leeches")
            )
            estimated_download_seconds = self._estimate_download_seconds(
                file_size=size,
                seeders=seeders,
                peers=peers,
            )

            if not self.query_relevance.is_relevant(
                query=query,
                title=title,
                description=description,
            ):
                continue

            download_url = magnet_url or enclosure_url or link

            if not download_url:
                continue

            quality = self.quality_ranker.evaluate(
                title=title,
                description=description,
                file_size=size,
            )

            if not quality.allowed:
                continue

            candidate_id = self._candidate_id(guid=guid, title=title, size=size)
            quality_note = (
                f"Подбор: {quality.quality_label}, "
                f"озвучка: {quality.audio_label}, "
                f"score={quality.score}."
            )

            full_description = self._join_description(
                description=description,
                quality_note=quality_note,
            )

            candidate = MediaCandidate(
                id=candidate_id,
                title=title,
                original_title=title,
                year=self._extract_year(title),
                media_type=MediaType.movie,
                description=full_description,
                source=self.name,
                license_mode=LicenseMode.unknown,
                file_name=None,
                relative_path=None,
                item_identifier=candidate_id,
                download_url=download_url,
                file_size=size,
                quality_label=quality.quality_label,
                audio_label=quality.audio_label,
                rank_score=quality.score,
                size_gb=round(size / (1024 ** 3), 2) if size else None,
                seeders=seeders,
                peers=peers,
                estimated_download_seconds=estimated_download_seconds,
            )

            release_key = self._release_key(title=title, size=size)
            source_priority = self._download_source_priority(download_url)

            existing = best_by_release_key.get(release_key)

            if existing is None:
                best_by_release_key[release_key] = (
                    quality.score,
                    source_priority,
                    candidate,
                )
                continue

            existing_score, existing_source_priority, _ = existing

            if (quality.score, source_priority) > (
                existing_score,
                existing_source_priority,
            ):
                best_by_release_key[release_key] = (
                    quality.score,
                    source_priority,
                    candidate,
                )

        ranked_candidates = sorted(
            best_by_release_key.values(),
            key=lambda value: value[0],
            reverse=True,
        )

        return [
            candidate
            for _, _, candidate in ranked_candidates[: self.settings.jackett_search_limit]
        ]

    def _clean_description(self, value: str | None) -> str | None:
        if not value:
            return None

        value = html.unescape(value)
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"\s+", " ", value).strip()

        return value or None

    def _join_description(self, description: str | None, quality_note: str) -> str:
        if description:
            return f"{description}\n\n{quality_note}"

        return quality_note

    def _release_key(self, title: str, size: int | None) -> str:
        normalized_title = re.sub(r"\s+", " ", title.lower()).strip()
        normalized_title = re.sub(r"[^a-zа-яё0-9 ]+", "", normalized_title)

        return f"{normalized_title}:{size or 0}"

    def _estimate_download_seconds(
        self,
        file_size: int | None,
        seeders: int | None,
        peers: int | None,
    ) -> int | None:
        if not file_size or file_size <= 0:
            return None

        seed_count = seeders if seeders is not None else 0
        peer_count = peers if peers is not None else 0

        if seed_count >= 50:
            bytes_per_second = 8 * 1024 * 1024
        elif seed_count >= 20:
            bytes_per_second = 4 * 1024 * 1024
        elif seed_count >= 10:
            bytes_per_second = 2 * 1024 * 1024
        elif seed_count >= 5:
            bytes_per_second = 1 * 1024 * 1024
        elif seed_count >= 1:
            bytes_per_second = 512 * 1024
        else:
            bytes_per_second = 256 * 1024

        if seed_count > 0 and peer_count > seed_count * 3:
            bytes_per_second = int(bytes_per_second * 0.75)

        return max(60, int(file_size / max(1, bytes_per_second)))


    def _download_source_priority(self, download_url: str) -> int:
        if download_url.startswith("magnet:"):
            return 3

        if "magnet" in download_url.lower():
            return 2

        return 1

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

    def _find_text(self, element: ET.Element, tag_name: str) -> str | None:
        child = element.find(tag_name)

        if child is None or child.text is None:
            return None

        return child.text.strip()

    def _find_enclosure_url(self, element: ET.Element) -> str | None:
        enclosure = element.find("enclosure")

        if enclosure is None:
            return None

        url = enclosure.attrib.get("url")

        if not url:
            return None

        return url.strip()

    def _find_enclosure_length(self, element: ET.Element) -> str | None:
        enclosure = element.find("enclosure")

        if enclosure is None:
            return None

        length = enclosure.attrib.get("length")

        if not length:
            return None

        return length.strip()

    def _find_torznab_attr(self, element: ET.Element, name: str) -> str | None:
        for child in list(element):
            if not child.tag.endswith("attr"):
                continue

            if child.attrib.get("name") != name:
                continue

            value = child.attrib.get("value")

            if not value:
                return None

            return value.strip()

        return None

    def _candidate_id(self, guid: str, title: str, size: int | None) -> str:
        stable_source = guid or title
        raw_value = f"{stable_source}:{title}:{size or 0}"
        digest = hashlib.sha1(raw_value.encode("utf-8")).hexdigest()[:16]
        readable = self._safe_slug(title)[:80]

        return f"jackett-{readable}-{digest}"

    def _safe_slug(self, value: str) -> str:
        value = quote(value, safe="")
        value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
        value = value.strip("._-")

        return value or "result"

    def _extract_year(self, value: str) -> int | None:
        match = re.search(r"\b(18|19|20)\d{2}\b", value)

        if not match:
            return None

        return int(match.group(0))

    def _parse_int(self, value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except ValueError:
            return None
        except TypeError:
            return None
