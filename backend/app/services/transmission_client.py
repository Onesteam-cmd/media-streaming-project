import httpx

from app.core.config import get_settings


class TransmissionClient:
    def __init__(self) -> None:
        settings = get_settings()

        self.rpc_url = settings.transmission_rpc_url
        self.username = settings.transmission_rpc_username
        self.password = settings.transmission_rpc_password
        self.session_id: str | None = None

    def _auth(self) -> tuple[str, str] | None:
        if self.username and self.password:
            return (self.username, self.password)

        return None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }

        if self.session_id:
            headers["X-Transmission-Session-Id"] = self.session_id

        return headers

    def call(self, method: str, arguments: dict | None = None) -> dict:
        payload = {
            "method": method,
            "arguments": arguments or {},
        }

        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                self.rpc_url,
                json=payload,
                headers=self._headers(),
                auth=self._auth(),
            )

            if response.status_code == 409:
                self.session_id = response.headers.get("X-Transmission-Session-Id")

                response = client.post(
                    self.rpc_url,
                    json=payload,
                    headers=self._headers(),
                    auth=self._auth(),
                )

            response.raise_for_status()
            data = response.json()

        if data.get("result") != "success":
            raise RuntimeError(f"Transmission RPC error: {data.get('result')}")

        return data

    def session_get(self) -> dict:
        return self.call("session-get").get("arguments", {})

    def torrent_get(self) -> list[dict]:
        data = self.call(
            "torrent-get",
            {
                "fields": self._torrent_fields(),
            },
        )

        return data.get("arguments", {}).get("torrents", [])

    def torrent_get_by_id(self, torrent_id: int) -> dict | None:
        data = self.call(
            "torrent-get",
            {
                "ids": [torrent_id],
                "fields": self._torrent_fields(),
            },
        )

        torrents = data.get("arguments", {}).get("torrents", [])

        if not torrents:
            return None

        return torrents[0]

    def torrent_add(
        self,
        filename: str | None = None,
        download_dir: str | None = None,
        metainfo: str | None = None,
    ) -> dict:
        if not filename and not metainfo:
            raise ValueError("torrent_add requires filename or metainfo.")

        arguments = {}

        if metainfo:
            arguments["metainfo"] = metainfo
        else:
            arguments["filename"] = filename

        if download_dir:
            arguments["download-dir"] = download_dir

        data = self.call("torrent-add", arguments)

        args = data.get("arguments", {})

        return (
            args.get("torrent-added")
            or args.get("torrent-duplicate")
            or {}
        )

    def torrent_remove(self, torrent_id: int, delete_local_data: bool = True) -> None:
        self.call(
            "torrent-remove",
            {
                "ids": [torrent_id],
                "delete-local-data": delete_local_data,
            },
        )

    def _torrent_fields(self) -> list[str]:
        return [
            "id",
            "name",
            "status",
            "percentDone",
            "error",
            "errorString",
            "downloadDir",
            "totalSize",
            "files",
            "peersConnected",
            "rateDownload",
            "eta",
        ]
