import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.services.jellyfin_client import JellyfinClient

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/jellyfin", tags=["jellyfin"], dependencies=[Depends(get_current_user_id)])


def _safe_http_error(exc: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": "Jellyfin вернул ошибку.",
            "status_code": exc.response.status_code,
        },
    )


def _safe_request_error(exc: httpx.RequestError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": "Backend не смог подключиться к Jellyfin.",
            "error": str(exc),
        },
    )


@router.get("/status")
def jellyfin_status() -> dict:
    try:
        client = JellyfinClient()
        info = client.get_system_info()

        return {
            "connected": True,
            "server_name": info.get("ServerName"),
            "version": info.get("Version"),
            "operating_system": info.get("OperatingSystem"),
            "startup_wizard_completed": info.get("StartupWizardCompleted"),
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc


@router.get("/libraries")
def jellyfin_libraries() -> dict:
    try:
        client = JellyfinClient()
        items = client.get_virtual_folders()

        libraries = []

        for item in items:
            libraries.append(
                {
                    "id": item.get("ItemId"),
                    "name": item.get("Name"),
                    "collection_type": item.get("CollectionType"),
                    "locations": item.get("Locations", []),
                }
            )

        return {
            "count": len(libraries),
            "items": libraries,
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc


@router.post("/scan")
def jellyfin_scan() -> dict:
    try:
        client = JellyfinClient()
        client.refresh_library()

        return {
            "status": "scan_requested",
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc
