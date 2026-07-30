from fastapi import HTTPException

from app.adapters.base import IngestAdapter
from app.adapters.external_source_template import ExternalSourceTemplateAdapter
from app.adapters.internet_archive import InternetArchiveAdapter
from app.adapters.jackett_adapter import JackettAdapter
from app.adapters.local_demo import LocalDemoAdapter
from app.adapters.supervised_external import SupervisedExternalAdapter
from app.adapters.torrent_demo import TorrentDemoAdapter
from app.core.config import get_settings
from app.models.schemas import AdapterInfo


def get_available_adapters() -> list[AdapterInfo]:
    settings = get_settings()

    raw_adapters = [
        {
            "name": LocalDemoAdapter.name,
            "title": LocalDemoAdapter.title,
            "description": LocalDemoAdapter.description,
            "enabled": True,
        },
        {
            "name": InternetArchiveAdapter.name,
            "title": InternetArchiveAdapter.title,
            "description": InternetArchiveAdapter.description,
            "enabled": True,
        },
        {
            "name": TorrentDemoAdapter.name,
            "title": TorrentDemoAdapter.title,
            "description": TorrentDemoAdapter.description,
            "enabled": True,
        },
        {
            "name": JackettAdapter.name,
            "title": JackettAdapter.title,
            "description": JackettAdapter.description,
            "enabled": bool(settings.jackett_api_key),
        },
        {
            "name": ExternalSourceTemplateAdapter.name,
            "title": ExternalSourceTemplateAdapter.title,
            "description": ExternalSourceTemplateAdapter.description,
            "enabled": False,
        },
        {
            "name": SupervisedExternalAdapter.name,
            "title": SupervisedExternalAdapter.title,
            "description": SupervisedExternalAdapter.description,
            "enabled": False,
        },
    ]

    return [
        AdapterInfo(
            name=item["name"],
            title=item["title"],
            description=item["description"],
            enabled=item["enabled"],
            active=item["name"] == settings.ingest_adapter,
        )
        for item in raw_adapters
    ]


def get_adapter_by_name(name: str) -> IngestAdapter:
    if name == LocalDemoAdapter.name:
        return LocalDemoAdapter()

    if name == InternetArchiveAdapter.name:
        return InternetArchiveAdapter()

    if name == TorrentDemoAdapter.name:
        return TorrentDemoAdapter()

    if name == JackettAdapter.name:
        return JackettAdapter()

    if name == ExternalSourceTemplateAdapter.name:
        return ExternalSourceTemplateAdapter()

    if name == SupervisedExternalAdapter.name:
        return SupervisedExternalAdapter()

    raise HTTPException(
        status_code=500,
        detail=f"Неизвестный ingest adapter: {name}",
    )


def get_active_adapter() -> IngestAdapter:
    settings = get_settings()
    return get_adapter_by_name(settings.ingest_adapter)
