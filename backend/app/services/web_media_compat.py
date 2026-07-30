from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import Any

from app.core.config import get_settings


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
    ".avi",
    ".mov",
    ".mkv",
}

WEB_CONTAINER_EXTENSIONS = {
    ".mp4",
    ".m4v",
}

WEB_VIDEO_CODECS = {
    "h264",
}

WEB_AUDIO_CODECS = {
    "aac",
    "mp3",
}


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return value


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _ffprobe(path: Path) -> dict[str, Any]:
    completed = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )

    stdout = _decode_process_output(completed.stdout)
    stderr = _decode_process_output(completed.stderr)

    if completed.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {stderr or stdout}")

    try:
        return json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe returned invalid JSON for {path}: {exc}") from exc


def _streams(info: dict[str, Any], codec_type: str) -> list[dict[str, Any]]:
    return [
        stream
        for stream in info.get("streams", [])
        if stream.get("codec_type") == codec_type
    ]


def _duration_seconds(info: dict[str, Any]) -> float | None:
    raw_value = (info.get("format") or {}).get("duration")

    if raw_value is None:
        return None

    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _is_web_compatible(path: Path, info: dict[str, Any]) -> bool:
    if path.suffix.lower() not in WEB_CONTAINER_EXTENSIONS:
        return False

    video_streams = _streams(info, "video")
    audio_streams = _streams(info, "audio")

    if not video_streams:
        return False

    video_codec = (video_streams[0].get("codec_name") or "").lower()
    audio_codec = (audio_streams[0].get("codec_name") or "").lower() if audio_streams else ""

    if video_codec not in WEB_VIDEO_CODECS:
        return False

    if audio_streams and audio_codec not in WEB_AUDIO_CODECS:
        return False

    return True


def _safe_stem(path: Path) -> str:
    stem = path.stem

    for suffix in [".tmp", ".partial"]:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]

    return stem


def _target_paths(source: Path) -> tuple[Path, Path]:
    settings = get_settings()
    media_root = Path(settings.media_root).resolve()
    movies_dir = Path(settings.movies_dir).resolve()

    stem = _safe_stem(source)

    if stem.endswith(".H264.DD51"):
        stem = stem[: -len(".H264.DD51")]

    if stem.endswith(".DD51"):
        stem = stem[: -len(".DD51")]

    try:
        source.resolve().relative_to(media_root)
        output_dir = source.parent
    except ValueError:
        output_dir = movies_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    final_path = output_dir / f"{stem}.H264.AAC.mp4"
    tmp_path = output_dir / f"{stem}.H264.AAC.tmp.mp4"

    return final_path, tmp_path


def _expected_min_size(expected_size: int | None) -> int:
    if not expected_size or expected_size <= 100_000_000:
        return 1

    return int(expected_size * 0.9)


def _assert_source_size(source: Path, expected_size: int | None) -> None:
    size = source.stat().st_size
    minimum = _expected_min_size(expected_size)

    if size < minimum:
        raise RuntimeError(
            f"Файл выглядит неполным: {source} ({size} bytes, expected at least {minimum} bytes)."
        )


def _assert_output_valid(source_info: dict[str, Any], output: Path) -> None:
    if not output.exists():
        raise RuntimeError(f"Конвертация не создала файл: {output}")

    if output.stat().st_size <= 1_000_000:
        raise RuntimeError(f"Конвертированный файл слишком маленький: {output}")

    output_info = _ffprobe(output)

    if not _is_web_compatible(output, output_info):
        raise RuntimeError(f"Конвертированный файл не web-compatible: {output}")

    source_duration = _duration_seconds(source_info)
    output_duration = _duration_seconds(output_info)

    if source_duration and output_duration:
        if output_duration < source_duration * 0.95:
            raise RuntimeError(
                f"Конвертированный файл короче исходника: source={source_duration}, output={output_duration}"
            )


def _convert_to_web_mp4(source: Path, source_info: dict[str, Any]) -> Path:
    final_path, tmp_path = _target_paths(source)

    if final_path.exists():
        final_info = _ffprobe(final_path)

        if _is_web_compatible(final_path, final_info):
            _assert_output_valid(source_info, final_path)
            return final_path

        final_path.unlink()

    if tmp_path.exists():
        tmp_path.unlink()

    video_streams = _streams(source_info, "video")
    video_codec = (video_streams[0].get("codec_name") or "").lower() if video_streams else ""

    if video_codec == "h264":
        video_args = ["-c:v", "copy"]
    else:
        video_args = [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *video_args,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp_path),
    ]

    completed = _run_command(command)

    if completed.returncode != 0:
        stdout = _decode_process_output(completed.stdout)
        stderr = _decode_process_output(completed.stderr)

        if tmp_path.exists():
            tmp_path.unlink()

        raise RuntimeError(
            "ffmpeg web-compatible conversion failed: "
            + (stderr or stdout)[-4000:]
        )

    tmp_path.replace(final_path)
    _assert_output_valid(source_info, final_path)

    return final_path


def _is_inside_media_root(path: Path) -> bool:
    settings = get_settings()
    media_root = Path(settings.media_root).resolve()

    try:
        path.resolve().relative_to(media_root)
        return True
    except ValueError:
        return False


def _unique_media_target(source: Path) -> Path:
    settings = get_settings()
    movies_dir = Path(settings.movies_dir).resolve()
    movies_dir.mkdir(parents=True, exist_ok=True)

    target = movies_dir / source.name

    if not target.exists() or target.stat().st_size == source.stat().st_size:
        return target

    for index in range(1, 1000):
        candidate = movies_dir / f"{source.stem}-{index}{source.suffix}"

        if not candidate.exists() or candidate.stat().st_size == source.stat().st_size:
            return candidate

    raise RuntimeError(f"Не удалось подобрать имя файла в медиатеке для {source.name}")


def _copy_or_link_to_media_library(source: Path) -> Path:
    target = _unique_media_target(source)

    if target.exists() and target.stat().st_size == source.stat().st_size:
        return target

    tmp_path = target.with_name(f"{target.stem}.copying{target.suffix}")

    if tmp_path.exists():
        tmp_path.unlink()

    try:
        os.link(source, target)
        return target
    except OSError:
        pass

    shutil.copy2(source, tmp_path)
    tmp_path.replace(target)

    return target


def _relative_to_media_root(path: Path) -> str:
    settings = get_settings()
    media_root = Path(settings.media_root).resolve()

    return path.resolve().relative_to(media_root).as_posix()


def _result_with_updates(result: Any, updates: dict[str, Any]) -> Any:
    if hasattr(result, "model_copy"):
        return result.model_copy(update=updates)

    if is_dataclass(result):
        return replace(result, **updates)

    for key, value in updates.items():
        setattr(result, key, value)

    return result


def ensure_web_compatible_prepare_result(
    result: Any,
    *,
    expected_size: int | None = None,
) -> Any:
    status = getattr(getattr(result, "status", None), "value", getattr(result, "status", None))

    if status != "completed":
        return result

    output_path = getattr(result, "output_path", None)

    if not output_path:
        return _result_with_updates(
            result,
            {
                "status": "failed",
                "progress": 0,
                "error_message": "Подготовка завершилась без output_path.",
            },
        )

    source = Path(output_path)

    if not source.exists() or not source.is_file():
        return _result_with_updates(
            result,
            {
                "status": "failed",
                "progress": 0,
                "error_message": f"Готовый файл не найден: {source}",
            },
        )

    try:
        _assert_source_size(source, expected_size)
        source_info = _ffprobe(source)

        if _is_web_compatible(source, source_info):
            if _is_inside_media_root(source):
                final_path = source
            else:
                final_path = _copy_or_link_to_media_library(source)
        else:
            final_path = _convert_to_web_mp4(source, source_info)

            settings = get_settings()
            movies_dir = Path(settings.movies_dir).resolve()

            try:
                source.resolve().relative_to(movies_dir)
                if source != final_path and source.exists():
                    source.unlink()
            except ValueError:
                pass

        return _result_with_updates(
            result,
            {
                "output_path": str(final_path),
                "file_name": final_path.name,
                "relative_path": _relative_to_media_root(final_path),
                "file_size": final_path.stat().st_size,
                "progress": 100,
                "error_message": None,
            },
        )

    except Exception as exc:
        return _result_with_updates(
            result,
            {
                "status": "failed",
                "progress": 0,
                "error_message": str(exc),
            },
        )
