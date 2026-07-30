import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}

MOBILE_SAFE_VIDEO_CODECS = {"h264"}
MOBILE_SAFE_AUDIO_CODECS = {"aac", "mp3"}


class MediaImportService:
    def copy_video_to_movies(
        self,
        source_path: Path,
        movies_dir: Path,
        output_name: str,
    ) -> Path:
        if not source_path.exists():
            raise FileNotFoundError(f"Исходный файл не найден: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"Источник не является файлом: {source_path}")

        if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Файл не похож на видео: {source_path}")

        movies_dir.mkdir(parents=True, exist_ok=True)

        safe_output_name = self._safe_filename(output_name)
        source_suffix = source_path.suffix.lower()

        if Path(safe_output_name).suffix.lower() not in VIDEO_EXTENSIONS:
            safe_output_name = safe_output_name + source_suffix

        probe = self._probe_video(source_path)

        if self._needs_mobile_mp4(source_path=source_path, probe=probe):
            output_path = movies_dir / Path(safe_output_name).with_suffix(".mp4").name

            if output_path.exists() and output_path.stat().st_size > 0:
                return output_path

            self._convert_to_mobile_mp4(
                source_path=source_path,
                output_path=output_path,
                probe=probe,
            )

            return output_path

        output_path = movies_dir / safe_output_name

        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path

        shutil.copy2(source_path, output_path)

        return output_path

    def find_first_video_file(self, root_dir: Path) -> Path | None:
        if not root_dir.exists():
            return None

        if root_dir.is_file() and root_dir.suffix.lower() in VIDEO_EXTENSIONS:
            return root_dir

        for path in sorted(root_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                return path

        return None

    def _probe_video(self, source_path: Path) -> dict[str, Any] | None:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(source_path),
                ],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError:
            return None
        except subprocess.CalledProcessError:
            return None

        try:
            stdout = result.stdout.decode("utf-8", errors="replace")
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None

    def _needs_mobile_mp4(self, source_path: Path, probe: dict[str, Any] | None) -> bool:
        if source_path.suffix.lower() != ".mp4":
            return True

        if probe is None:
            return False

        streams = probe.get("streams") or []

        video_codecs = {
            stream.get("codec_name")
            for stream in streams
            if stream.get("codec_type") == "video"
        }

        audio_codecs = {
            stream.get("codec_name")
            for stream in streams
            if stream.get("codec_type") == "audio"
        }

        if not video_codecs:
            return True

        if not video_codecs.issubset(MOBILE_SAFE_VIDEO_CODECS):
            return True

        if audio_codecs and not audio_codecs.issubset(MOBILE_SAFE_AUDIO_CODECS):
            return True

        for stream in streams:
            if stream.get("codec_type") == "audio":
                channels = stream.get("channels")
                if isinstance(channels, int) and channels > 2:
                    return True

        return False

    def _convert_to_mobile_mp4(
        self,
        source_path: Path,
        output_path: Path,
        probe: dict[str, Any] | None,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_suffix(".tmp.mp4")

        video_codec = self._main_video_codec(probe)

        if video_codec in MOBILE_SAFE_VIDEO_CODECS:
            video_args = ["-c:v", "copy"]
        else:
            video_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]

        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            *video_args,
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(temp_path),
        ]

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            if temp_path.exists():
                temp_path.unlink()

            if exc.stderr:
                stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            else:
                stderr = str(exc)

            raise RuntimeError(f"ffmpeg conversion failed: {stderr}") from exc

        temp_path.replace(output_path)

    def _main_video_codec(self, probe: dict[str, Any] | None) -> str | None:
        if probe is None:
            return None

        for stream in probe.get("streams") or []:
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name")
                return str(codec_name) if codec_name else None

        return None

    def _safe_filename(self, value: str) -> str:
        raw_value = value.strip()
        suffix = Path(raw_value).suffix.lower()

        safe_chars = []

        for char in raw_value:
            if char.isalnum() or char in {".", "_", "-"}:
                safe_chars.append(char)
            else:
                safe_chars.append("_")

        result = "".join(safe_chars).strip("._")

        if not result:
            return "imported_video"

        # Большинство файловых систем ограничивают одно имя файла 255 байтами.
        # Держим запас, потому что кириллица и спецсимволы могут занимать больше байт.
        max_length = 180

        if len(result) <= max_length:
            return result

        if suffix and result.lower().endswith(suffix):
            base = result[: max_length - len(suffix)].strip("._")
            return f"{base}{suffix}"

        return result[:max_length].strip("._")
