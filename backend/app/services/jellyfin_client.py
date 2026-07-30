import httpx

from app.core.config import get_settings


class JellyfinClient:
    def __init__(self) -> None:
        settings = get_settings()

        self.base_url = settings.jellyfin_url.rstrip("/")
        self.api_key = settings.jellyfin_api_key

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("JELLYFIN_API_KEY не настроен.")

        return {
            "Authorization": (
                'MediaBrowser '
                'Client="media-backend", '
                'Device="backend", '
                'DeviceId="media-backend", '
                'Version="0.1.0", '
                f'Token="{self.api_key}"'
            ),
            "X-Emby-Token": self.api_key,
        }

    def _request(self, method: str, path: str) -> dict | list | None:
        url = f"{self.base_url}{path}"

        with httpx.Client(timeout=10.0) as client:
            response = client.request(
                method=method,
                url=url,
                headers=self._headers(),
            )

            response.raise_for_status()

            if not response.content:
                return None

            return response.json()

    def get_system_info(self) -> dict:
        result = self._request("GET", "/System/Info")

        if not isinstance(result, dict):
            return {}

        return result

    def get_virtual_folders(self) -> list[dict]:
        result = self._request("GET", "/Library/VirtualFolders")

        if not isinstance(result, list):
            return []

        return result

    def refresh_library(self) -> None:
        try:
            self._request("POST", "/Library/Refresh")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 405}:
                self._request("GET", "/Library/Refresh")
                return

            raise
