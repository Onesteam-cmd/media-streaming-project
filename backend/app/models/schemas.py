from pydantic import BaseModel, Field

from app.models.enums import IngestStatus, LicenseMode, MediaType, RequestStatus


class MediaCandidate(BaseModel):
    id: str
    title: str
    original_title: str | None = None
    year: int | None = None
    media_type: MediaType = MediaType.movie
    description: str | None = None
    source: str
    license_mode: LicenseMode = LicenseMode.unknown
    file_name: str | None = None
    relative_path: str | None = None

    item_identifier: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    quality_label: str | None = None
    audio_label: str | None = None
    rank_score: int | None = None
    size_gb: float | None = None
    duration_seconds: int | None = None
    seeders: int | None = None
    peers: int | None = None
    estimated_download_seconds: int | None = None


class SearchRequest(BaseModel):
    query: str = ""
    year: int | None = None
    max_size_gb: float | None = None
    prefer_quality: str | None = None
    limit: int = Field(default=5, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class SearchResponse(BaseModel):
    query: str
    count: int
    limit: int = 5
    offset: int = 0
    has_more: bool = False
    items: list[MediaCandidate]


class MediaRequestCreate(BaseModel):
    candidate_id: str = Field(min_length=1)


class MediaRequestRead(BaseModel):
    id: str
    user_id: str = "default"
    candidate_id: str
    status: RequestStatus
    error_message: str | None = None


class IngestJobRead(BaseModel):
    id: str
    request_id: str
    adapter_name: str
    candidate_id: str
    status: IngestStatus
    progress: int = Field(default=0, ge=0, le=100)
    output_path: str | None = None
    error_message: str | None = None
    external_id: str | None = None
    download_speed_kbps: float | None = None
    eta_seconds: int | None = None
    peers_connected: int | None = None


class MediaCandidateSummary(BaseModel):
    id: str
    title: str
    source: str
    year: int | None = None
    file_name: str | None = None
    relative_path: str | None = None


class MediaRequestDetail(BaseModel):
    request: MediaRequestRead
    job: IngestJobRead | None = None
    candidate: MediaCandidateSummary | None = None


class AdapterInfo(BaseModel):
    name: str
    title: str
    description: str
    enabled: bool
    active: bool


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=256)
    invite_code: str | None = None


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=256)


class AuthChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)


class AuthUserRead(BaseModel):
    id: str
    username: str


class AuthTokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: AuthUserRead


class WatchPositionRead(BaseModel):
    media_id: str
    position_seconds: int = Field(default=0, ge=0)


class WatchPositionUpdate(BaseModel):
    position_seconds: int = Field(default=0, ge=0)
