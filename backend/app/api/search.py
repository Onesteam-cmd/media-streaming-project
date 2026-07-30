from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.registry import get_active_adapter, get_adapter_by_name, get_available_adapters
from app.core.config import get_settings
from app.db.session import get_db
from app.models.schemas import MediaCandidate, SearchRequest, SearchResponse
from app.models.tables import MediaCandidateTable
from app.services.mappers import candidate_schema_to_table, update_candidate_table
from app.services.search_ranking import SearchResultRanker

from app.services.user_context import get_current_user_id

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(get_current_user_id)])
search_ranker = SearchResultRanker()


def _save_candidates(items: list[MediaCandidate], db: Session) -> None:
    for item in items:
        existing = db.get(MediaCandidateTable, item.id)

        if existing is None:
            db.add(candidate_schema_to_table(item))
        else:
            update_candidate_table(existing, item)

    db.commit()


def _public_candidate(item: MediaCandidate) -> MediaCandidate:
    return item.model_copy(
        update={
            "download_url": None,
        }
    )


def _paginate_items(
    items: list[MediaCandidate],
    payload: SearchRequest,
) -> tuple[list[MediaCandidate], int, bool]:
    total = len(items)
    start = payload.offset
    end = payload.offset + payload.limit
    page_items = items[start:end]
    has_more = end < total

    return page_items, total, has_more


@router.post("", response_model=SearchResponse)
def search_media(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    adapter = get_active_adapter()
    items = adapter.search(payload.query)
    ranked_items = search_ranker.rank(items, payload)

    _save_candidates(ranked_items, db)

    page_items, total, has_more = _paginate_items(ranked_items, payload)

    public_items = [
        _public_candidate(item)
        for item in page_items
    ]

    return SearchResponse(
        query=payload.query,
        count=total,
        limit=payload.limit,
        offset=payload.offset,
        has_more=has_more,
        items=public_items,
    )


@router.post("/all")
def search_all_sources(payload: SearchRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    requested_adapter_names = settings.enabled_user_search_adapters()

    adapters = [
        item
        for item in get_available_adapters()
        if item.enabled and (
            not requested_adapter_names
            or item.name in requested_adapter_names
        )
    ]

    all_items: list[MediaCandidate] = []
    errors = {}

    for adapter_info in adapters:
        try:
            adapter = get_adapter_by_name(adapter_info.name)
            items = adapter.search(payload.query)
            all_items.extend(items)
        except Exception as exc:
            errors[adapter_info.name] = str(exc)

    ranked_items = search_ranker.rank(all_items, payload)

    _save_candidates(ranked_items, db)

    page_items, total, has_more = _paginate_items(ranked_items, payload)

    public_items = [
        _public_candidate(item)
        for item in page_items
    ]

    return {
        "query": payload.query,
        "count": total,
        "limit": payload.limit,
        "offset": payload.offset,
        "has_more": has_more,
        "items": public_items,
        "errors": errors,
    }
