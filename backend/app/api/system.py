from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.config import get_settings

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(get_current_user_id)])


def _sqlite_path_from_url(database_url: str) -> str | None:
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)

    return None


@router.get("/status")
def system_status() -> dict:
    settings = get_settings()

    media_root = Path(settings.media_root)
    movies_dir = Path(settings.movies_dir)
    catalog_path = Path(settings.local_catalog_path)

    sqlite_path_raw = _sqlite_path_from_url(settings.database_url)
    sqlite_path = Path(sqlite_path_raw) if sqlite_path_raw else None

    return {
        "status": "ok",
        "project": settings.project_name,
        "timezone": settings.timezone,
        "active_adapter": settings.ingest_adapter,
        "paths": {
            "media_root": {
                "path": str(media_root),
                "exists": media_root.exists(),
                "is_dir": media_root.is_dir(),
            },
            "movies_dir": {
                "path": str(movies_dir),
                "exists": movies_dir.exists(),
                "is_dir": movies_dir.is_dir(),
            },
            "local_catalog": {
                "path": str(catalog_path),
                "exists": catalog_path.exists(),
                "is_file": catalog_path.is_file(),
            },
            "sqlite_db": {
                "path": str(sqlite_path) if sqlite_path else None,
                "exists": sqlite_path.exists() if sqlite_path else False,
                "is_file": sqlite_path.is_file() if sqlite_path else False,
            },
        },
        "jellyfin": {
            "url": settings.jellyfin_url,
            "api_key_configured": bool(settings.jellyfin_api_key),
        },
    }
