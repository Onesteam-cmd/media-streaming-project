import re

from app.models.schemas import MediaCandidate, SearchRequest


COLLECTION_PATTERNS = [
    r"\btrilogy\b",
    r"\bcollection\b",
    r"\bcomplete\b",
    r"\bpack\b",
    r"\bbox\s*set\b",
    r"\bсборник\b",
    r"\bтрилог",
    r"\bколлекц",
    r"\bдилог",
    r"\bтетралог",
]


MULTI_YEAR_PATTERNS = [
    r"\b(18|19|20)\d{2}\s*[-–]\s*(18|19|20)\d{2}\b",
]


SEQUEL_HINTS = [
    r"\breloaded\b",
    r"\brevolutions\b",
    r"\bresurrections\b",
    r"перезагруз",
    r"революц",
    r"воскреш",
]


DOCUMENTARY_HINTS = [
    r"\bdocumentary\b",
    r"\bglitch\b",
    r"документ",
]


class SearchResultRanker:
    def rank(
        self,
        items: list[MediaCandidate],
        payload: SearchRequest,
    ) -> list[MediaCandidate]:
        filtered_items = [
            item
            for item in items
            if self._passes_hard_filters(item, payload)
        ]

        scored_items = [
            (self._score(item, payload), item)
            for item in filtered_items
        ]

        scored_items.sort(
            key=lambda pair: pair[0],
            reverse=True,
        )

        return [
            item
            for _, item in scored_items
        ]

    def _passes_hard_filters(self, item: MediaCandidate, payload: SearchRequest) -> bool:
        if payload.max_size_gb is None or not item.file_size:
            return True

        size_gb = item.file_size / (1024 ** 3)

        return size_gb <= payload.max_size_gb

    def _score(self, item: MediaCandidate, payload: SearchRequest) -> int:
        text = self._normalize(" ".join([
            item.title or "",
            item.original_title or "",
            item.description or "",
        ]))

        score = 0
        score += self._existing_quality_score(item)
        score += self._year_score(item, payload.year)
        score += self._size_score(item, payload.max_size_gb)
        score += self._preferred_quality_score(text, payload.prefer_quality)
        score += self._single_movie_score(text, payload.year)

        return score

    def _existing_quality_score(self, item: MediaCandidate) -> int:
        description = item.description or ""
        match = re.search(r"score=(-?\d+)", description)

        if not match:
            return 0

        return int(match.group(1))

    def _year_score(self, item: MediaCandidate, requested_year: int | None) -> int:
        if requested_year is None:
            return 0

        if item.year == requested_year:
            return 100

        if item.year is None:
            return -20

        distance = abs(item.year - requested_year)

        if distance <= 1:
            return 10

        return -120

    def _size_score(self, item: MediaCandidate, max_size_gb: float | None) -> int:
        if max_size_gb is None or not item.file_size:
            return 0

        size_gb = item.file_size / (1024 ** 3)

        if 2 <= size_gb <= max_size_gb:
            return 25

        if 0.7 <= size_gb < 2:
            return 5

        if size_gb < 0.7:
            return -25

        return 0

    def _preferred_quality_score(self, text: str, prefer_quality: str | None) -> int:
        if not prefer_quality:
            return 0

        quality = prefer_quality.lower().strip()

        if quality in {"1080", "1080p", "fullhd", "fhd"}:
            if "1080p" in text or "fhd" in text:
                return 55

            if "2160p" in text or "4k" in text or "uhd" in text:
                return -45

            if "720p" in text:
                return -15

        if quality in {"4k", "2160", "2160p", "uhd"}:
            if "2160p" in text or "4k" in text or "uhd" in text:
                return 55

            if "1080p" in text:
                return 10

        if quality in {"720", "720p", "hd"}:
            if "720p" in text:
                return 40

            if "1080p" in text:
                return 15

            if "2160p" in text or "4k" in text:
                return -45

        return 0

    def _single_movie_score(self, text: str, requested_year: int | None) -> int:
        score = 0

        if self._matches_any(text, COLLECTION_PATTERNS):
            score -= 100

        if requested_year is not None and self._matches_any(text, MULTI_YEAR_PATTERNS):
            score -= 120

        if requested_year is not None and self._matches_any(text, SEQUEL_HINTS):
            score -= 90

        if self._matches_any(text, DOCUMENTARY_HINTS):
            score -= 70

        return score

    def _normalize(self, value: str) -> str:
        value = value.lower()
        value = value.replace("ё", "е")
        value = re.sub(r"[^a-zа-я0-9\-–]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()

        return value

    def _matches_any(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)
