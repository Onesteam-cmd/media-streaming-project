import html
import re


TITLE_ALIASES: dict[str, list[str]] = {
    "матрица": ["matrix", "the matrix", "матрица"],
    "matrix": ["matrix", "the matrix", "матрица"],
}


class QueryRelevanceFilter:
    def is_relevant(
        self,
        query: str,
        title: str,
        description: str | None = None,
    ) -> bool:
        query_text = self._normalize(query)
        title_text = self._normalize(title)
        description_text = self._normalize(description or "")
        combined_text = f"{title_text} {description_text}"

        aliases = self._aliases_for_query(query_text)

        for alias in aliases:
            normalized_alias = self._normalize(alias)

            if normalized_alias and normalized_alias in combined_text:
                return True

        query_words = self._words(query_text)

        if not query_words:
            return True

        matched_words = [
            word
            for word in query_words
            if word in combined_text
        ]

        if len(query_words) == 1:
            return bool(matched_words)

        return len(matched_words) >= max(1, len(query_words) - 1)

    def _aliases_for_query(self, query_text: str) -> list[str]:
        aliases = {query_text}

        for key, values in TITLE_ALIASES.items():
            normalized_key = self._normalize(key)

            if normalized_key and normalized_key in query_text:
                aliases.update(values)

        return sorted(aliases, key=len, reverse=True)

    def _words(self, value: str) -> list[str]:
        return [
            word
            for word in re.findall(r"[a-zа-яё0-9]+", value)
            if len(word) >= 2
        ]

    def _normalize(self, value: str) -> str:
        value = html.unescape(value or "")
        value = value.lower()
        value = value.replace("ё", "е")
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"[^a-zа-я0-9]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()

        return value
