import re
from dataclasses import dataclass


BAD_CONTENT_PATTERNS = [
    r"\bxxx\b",
    r"\bporn\b",
    r"\bporno\b",
    r"\bsex\b",
    r"\bsexual\b",
    r"эротик",
    r"порно",
]


BAD_QUALITY_PATTERNS = [
    r"\bcamrip\b",
    r"\bcam\b",
    r"\bts\b",
    r"\btelesync\b",
    r"\btc\b",
    r"\btelecine\b",
    r"\bscreener\b",
    r"\bscr\b",
    r"\bdvdscr\b",
    r"\bwp\b",
    r"\bworkprint\b",
    r"\bhc\b",
    r"\bhdcam\b",
]


RUSSIAN_AUDIO_PATTERNS = [
    r"\brus\b",
    r"\bru\b",
    r"рус",
    r"русск",
    r"дубл",
    r"дублирован",
    r"профессиональн",
    r"многоголос",
    r"двухголос",
    r"одноголос",
    r"\bmvo\b",
    r"\bdvo\b",
    r"\bavo\b",
    r"\bdub\b",
    r"\bline\b",
    r"лиценз",
    r"чистый звук",
]


NON_RUSSIAN_OR_MIXED_AUDIO_PATTERNS = [
    r"\beng\b",
    r"\benglish\b",
    r"англ",
    r"оригинал",
    r"\boriginal\b",
    r"\bdual\b",
    r"dual audio",
    r"\bmulti\b",
    r"мультиязыч",
    r"субтитр",
    r"\bsubs?\b",
    r"\bsubbed\b",
    r"ukr",
    r"украин",
]


@dataclass(frozen=True)
class TorrentQualityResult:
    allowed: bool
    score: int
    quality_label: str
    audio_label: str
    reason: str | None = None


class TorrentQualityRanker:
    def __init__(
        self,
        require_russian_audio: bool = True,
        strict_russian_only: bool = True,
        exclude_bad_quality: bool = True,
    ) -> None:
        self.require_russian_audio = require_russian_audio
        self.strict_russian_only = strict_russian_only
        self.exclude_bad_quality = exclude_bad_quality

    def evaluate(
        self,
        title: str,
        description: str | None = None,
        file_size: int | None = None,
    ) -> TorrentQualityResult:
        text = self._normalize_text(" ".join([title or "", description or ""]))

        has_bad_content = self._matches_any(text, BAD_CONTENT_PATTERNS)
        has_russian_audio = self._matches_any(text, RUSSIAN_AUDIO_PATTERNS)
        has_non_russian_or_mixed_audio = self._matches_any(
            text,
            NON_RUSSIAN_OR_MIXED_AUDIO_PATTERNS,
        )
        has_bad_quality = self._matches_any(text, BAD_QUALITY_PATTERNS)

        if has_bad_content:
            return TorrentQualityResult(
                allowed=False,
                score=-1000,
                quality_label="bad_content",
                audio_label="unknown",
                reason="Неподходящий контент.",
            )

        if self.require_russian_audio and not has_russian_audio:
            return TorrentQualityResult(
                allowed=False,
                score=-1000,
                quality_label="unknown",
                audio_label="unknown",
                reason="Нет признаков русской озвучки.",
            )

        if self.strict_russian_only and has_non_russian_or_mixed_audio:
            return TorrentQualityResult(
                allowed=False,
                score=-1000,
                quality_label="unknown",
                audio_label="mixed_or_non_russian",
                reason="Есть признаки нерусской, смешанной или subtitle-only версии.",
            )

        if self.exclude_bad_quality and has_bad_quality:
            return TorrentQualityResult(
                allowed=False,
                score=-1000,
                quality_label="bad_quality",
                audio_label=self._audio_label(text),
                reason="Низкое качество релиза.",
            )

        score = 0
        score += self._quality_score(text)
        score += self._release_source_score(text)
        score += self._audio_score(text)
        score += self._codec_score(text)
        score += self._size_score(file_size)

        return TorrentQualityResult(
            allowed=True,
            score=score,
            quality_label=self._quality_label(text),
            audio_label=self._audio_label(text),
            reason=None,
        )

    def _quality_score(self, text: str) -> int:
        score = 0

        if re.search(r"\b2160p\b|\b4k\b|\buhd\b", text):
            score += 60
        elif re.search(r"\b1080p\b|\bfhd\b", text):
            score += 45
        elif re.search(r"\b720p\b|\bhd\b", text):
            score += 25
        elif re.search(r"\b480p\b|\bdvdrip\b|\bdvd\b", text):
            score += 5

        return score

    def _release_source_score(self, text: str) -> int:
        score = 0

        if re.search(r"\bremux\b|\bbdremux\b", text):
            score += 35
        elif re.search(r"\bbluray\b|\bbdrip\b|\bbd-rip\b", text):
            score += 28
        elif re.search(r"\bweb-dl\b|\bwebdl\b", text):
            score += 25
        elif re.search(r"\bwebrip\b", text):
            score += 18
        elif re.search(r"\bhdtv\b", text):
            score += 8

        return score

    def _audio_score(self, text: str) -> int:
        score = 0

        if re.search(r"дублирован|\b дуб\b|\bdub\b", text):
            score += 35
        elif re.search(r"многоголос|\bmvo\b", text):
            score += 25
        elif re.search(r"двухголос|\bdvo\b", text):
            score += 16
        elif re.search(r"одноголос|\bavo\b", text):
            score += 8

        if re.search(r"лиценз|чистый звук", text):
            score += 10

        if re.search(r"\bline\b", text):
            score -= 10

        return score

    def _codec_score(self, text: str) -> int:
        score = 0

        if re.search(r"\bhevc\b|\bx265\b|h\.?265", text):
            score += 8
        elif re.search(r"\bx264\b|h\.?264|\bavc\b", text):
            score += 6

        if re.search(r"\bhdr\b|\bdv\b|\bdolby vision\b", text):
            score += 5

        return score

    def _size_score(self, file_size: int | None) -> int:
        if not file_size:
            return 0

        size_gb = file_size / (1024 ** 3)

        if 2 <= size_gb <= 18:
            return 12

        if 0.7 <= size_gb < 2:
            return 5

        if size_gb > 40:
            return -10

        if size_gb < 0.7:
            return -8

        return 0

    def _quality_label(self, text: str) -> str:
        if re.search(r"\b2160p\b|\b4k\b|\buhd\b", text):
            return "2160p/4K"

        if re.search(r"\b1080p\b|\bfhd\b", text):
            return "1080p"

        if re.search(r"\b720p\b|\bhd\b", text):
            return "720p"

        if re.search(r"\bdvd\b|\bdvdrip\b", text):
            return "DVD"

        return "unknown"

    def _audio_label(self, text: str) -> str:
        if re.search(r"дублирован|\b дуб\b|\bdub\b", text):
            return "русский дубляж"

        if re.search(r"многоголос|\bmvo\b", text):
            return "русская многоголосая"

        if re.search(r"двухголос|\bdvo\b", text):
            return "русская двухголосая"

        if re.search(r"одноголос|\bavo\b", text):
            return "русская одноголосая"

        if re.search(r"\bline\b", text):
            return "русская line"

        if re.search(r"\brus\b|\bru\b|рус", text):
            return "русская"

        return "unknown"

    def _normalize_text(self, value: str) -> str:
        value = value.lower()
        value = value.replace(".", " ")
        value = value.replace("_", " ")
        value = value.replace("-", " ")
        value = re.sub(r"\s+", " ", value).strip()

        return value

    def _matches_any(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)
