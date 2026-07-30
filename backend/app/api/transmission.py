import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.models.transmission import TransmissionTorrentAddRequest
from app.services.transmission_client import TransmissionClient

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/transmission", tags=["transmission"], dependencies=[Depends(get_current_user_id)])


def _safe_http_error(exc: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": "Transmission вернул HTTP-ошибку.",
            "status_code": exc.response.status_code,
        },
    )


def _safe_request_error(exc: httpx.RequestError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": "Backend не смог подключиться к Transmission.",
            "error": str(exc),
        },
    )


@router.get("/status")
def transmission_status() -> dict:
    try:
        client = TransmissionClient()
        session = client.session_get()

        return {
            "connected": True,
            "version": session.get("version"),
            "rpc_version": session.get("rpc-version"),
            "download_dir": session.get("download-dir"),
            "incomplete_dir": session.get("incomplete-dir"),
            "incomplete_dir_enabled": session.get("incomplete-dir-enabled"),
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc


@router.get("/torrents")
def transmission_torrents() -> dict:
    try:
        client = TransmissionClient()
        torrents = client.torrent_get()

        return {
            "count": len(torrents),
            "items": torrents,
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc


@router.post("/torrents")
def transmission_add_torrent(payload: TransmissionTorrentAddRequest) -> dict:
    try:
        client = TransmissionClient()
        torrent = client.torrent_add(
            filename=payload.filename,
            download_dir=payload.download_dir,
        )

        return {
            "status": "added",
            "torrent": torrent,
        }

    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise _safe_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise _safe_request_error(exc) from exc

