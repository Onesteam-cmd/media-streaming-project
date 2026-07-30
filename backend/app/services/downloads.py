from pathlib import Path

import httpx


class DownloadService:
    def download_file(self, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_suffix(output_path.suffix + ".part")

        try:
            with httpx.Client(timeout=None, follow_redirects=True) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()

                    with temp_path.open("wb") as file:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            if chunk:
                                file.write(chunk)

            temp_path.replace(output_path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()

            raise
