from fastapi import APIRouter, Depends

from app.adapters.registry import get_available_adapters
from app.core.config import get_settings
from app.models.schemas import AdapterInfo

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/adapters", tags=["adapters"], dependencies=[Depends(get_current_user_id)])


@router.get("")
def list_adapters() -> dict[str, str | list[AdapterInfo]]:
    settings = get_settings()

    return {
        "active_adapter": settings.ingest_adapter,
        "adapters": get_available_adapters(),
    }
