import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.services.jellyfin_client import JellyfinClient
from app.services.transmission_client import TransmissionClient


router = APIRouter(prefix="/api/readiness", tags=["readiness"])


@router.get("")
def readiness() -> dict:
    settings = get_settings()

    checks = {
        "backend": True,
        "jellyfin": False,
        "transmission": False,
        "active_adapter": settings.ingest_adapter,
    }

    errors = {}

    try:
        JellyfinClient().get_system_info()
        checks["jellyfin"] = True
    except Exception as exc:
        errors["jellyfin"] = str(exc)

    try:
        TransmissionClient().session_get()
        checks["transmission"] = True
    except Exception as exc:
        errors["transmission"] = str(exc)

    ready = (
        checks["backend"]
        and checks["jellyfin"]
        and checks["transmission"]
    )

    return {
        "ready": ready,
        "checks": checks,
        "errors": errors,
    }
