from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.schemas import MediaCandidate
from app.models.tables import MediaCandidateTable
from app.services.mappers import candidate_table_to_schema

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/candidates", tags=["candidates"], dependencies=[Depends(get_current_user_id)])


def _public_candidate(item: MediaCandidate) -> MediaCandidate:
    return item.model_copy(
        update={
            "download_url": None,
        }
    )


@router.get("")
def list_candidates(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    count = db.scalar(
        select(func.count()).select_from(MediaCandidateTable)
    ) or 0

    rows = db.scalars(
        select(MediaCandidateTable)
        .order_by(MediaCandidateTable.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = [
        _public_candidate(candidate_table_to_schema(row))
        for row in rows
    ]

    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.get("/{candidate_id}")
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
) -> MediaCandidate:
    row = db.get(MediaCandidateTable, candidate_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found.",
        )

    return _public_candidate(candidate_table_to_schema(row))
