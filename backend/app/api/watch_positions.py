from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.schemas import WatchPositionRead, WatchPositionUpdate
from app.models.tables import WatchPositionTable
from app.services.user_context import get_current_user_id


router = APIRouter(prefix="/api/watch-positions", tags=["watch-positions"])


@router.get("")
def list_watch_positions(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    rows = db.scalars(
        select(WatchPositionTable)
        .where(WatchPositionTable.user_id == current_user_id)
        .order_by(WatchPositionTable.updated_at.desc())
    ).all()

    items = [
        WatchPositionRead(
            media_id=row.media_id,
            position_seconds=row.position_seconds,
        )
        for row in rows
        if row.position_seconds > 0
    ]

    return {
        "count": len(items),
        "items": items,
    }


@router.put("/{media_id}", response_model=WatchPositionRead)
def upsert_watch_position(
    media_id: str,
    payload: WatchPositionUpdate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> WatchPositionRead:
    now = datetime.utcnow()
    position_seconds = max(0, int(payload.position_seconds))

    row = db.scalars(
        select(WatchPositionTable)
        .where(WatchPositionTable.user_id == current_user_id)
        .where(WatchPositionTable.media_id == media_id)
    ).first()

    if row is None:
        row = WatchPositionTable(
            user_id=current_user_id,
            media_id=media_id,
            position_seconds=position_seconds,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.position_seconds = position_seconds
        row.updated_at = now

    db.commit()
    db.refresh(row)

    return WatchPositionRead(
        media_id=row.media_id,
        position_seconds=row.position_seconds,
    )


@router.delete("/{media_id}")
def delete_watch_position(
    media_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    row = db.scalars(
        select(WatchPositionTable)
        .where(WatchPositionTable.user_id == current_user_id)
        .where(WatchPositionTable.media_id == media_id)
    ).first()

    if row is not None:
        db.delete(row)
        db.commit()

    return {
        "status": "deleted",
        "media_id": media_id,
    }
