from fastapi import APIRouter, Depends

from app.core.config import get_settings

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/configuration", tags=["configuration"], dependencies=[Depends(get_current_user_id)])


@router.get("/summary")
def configuration_summary() -> dict:
    settings = get_settings()

    return {
        "project": {
            "name": settings.project_name,
            "timezone": settings.timezone,
        },
        "adapter": {
            "active": settings.ingest_adapter,
        },
        "paths": {
            "media_root": settings.media_root,
            "movies_dir": settings.movies_dir,
            "local_catalog_path": settings.local_catalog_path,
            "transmission_backend_downloads_dir": settings.transmission_backend_downloads_dir,
        },
        "jellyfin": {
            "url": settings.jellyfin_url,
            "api_key_configured": bool(settings.jellyfin_api_key),
        },
        "internet_archive": {
            "base_url": settings.internet_archive_base_url,
            "search_rows": settings.internet_archive_search_rows,
            "max_file_size_mb": settings.internet_archive_max_file_size_mb,
        },
        "transmission": {
            "rpc_url": settings.transmission_rpc_url,
            "username_configured": bool(settings.transmission_rpc_username),
            "password_configured": bool(settings.transmission_rpc_password),
        },
    }
