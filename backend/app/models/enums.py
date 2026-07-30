from enum import StrEnum


class MediaType(StrEnum):
    movie = "movie"
    series = "series"


class LicenseMode(StrEnum):
    demo = "demo"
    public_domain = "public_domain"
    creative_commons = "creative_commons"
    own_file = "own_file"
    unknown = "unknown"


class RequestStatus(StrEnum):
    created = "created"
    queued = "queued"
    running = "running"
    downloading = "downloading"
    importing = "importing"
    scanning = "scanning"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    deleted = "deleted"


class IngestStatus(StrEnum):
    queued = "queued"
    running = "running"
    downloading = "downloading"
    importing = "importing"
    scanning = "scanning"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
