from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = Field(default="Media Streaming Project", alias="PROJECT_NAME")
    timezone: str = Field(default="Europe/Moscow", alias="TZ")

    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    database_url: str = Field(default="sqlite:////app/data/app.db", alias="DATABASE_URL")

    content_provider: str = Field(default="multi_source", alias="CONTENT_PROVIDER")
    user_search_adapters: str = Field(default="", alias="USER_SEARCH_ADAPTERS")
    ingest_adapter: str = Field(default="local_demo", alias="INGEST_ADAPTER")

    media_root: str = Field(default="/media", alias="MEDIA_ROOT")
    movies_dir: str = Field(default="/media/movies", alias="MOVIES_DIR")
    media_public_base_url: str = Field(default="", alias="MEDIA_PUBLIC_BASE_URL")
    local_catalog_path: str = Field(
        default="/app/catalogs/local_catalog.json",
        alias="LOCAL_CATALOG_PATH",
    )

    jellyfin_url: str = Field(default="http://jellyfin:8096", alias="JELLYFIN_URL")
    jellyfin_api_key: str = Field(default="", alias="JELLYFIN_API_KEY")

    internet_archive_base_url: str = Field(
        default="https://archive.org",
        alias="INTERNET_ARCHIVE_BASE_URL",
    )
    internet_archive_search_rows: int = Field(
        default=5,
        alias="INTERNET_ARCHIVE_SEARCH_ROWS",
    )
    internet_archive_max_file_size_mb: int = Field(
        default=250,
        alias="INTERNET_ARCHIVE_MAX_FILE_SIZE_MB",
    )

    transmission_rpc_url: str = Field(
        default="http://transmission:9091/transmission/rpc",
        alias="TRANSMISSION_RPC_URL",
    )
    transmission_rpc_username: str = Field(
        default="",
        alias="TRANSMISSION_RPC_USERNAME",
    )
    transmission_rpc_password: str = Field(
        default="",
        alias="TRANSMISSION_RPC_PASSWORD",
    )
    transmission_backend_downloads_dir: str = Field(
        default="/downloads/transmission",
        alias="TRANSMISSION_BACKEND_DOWNLOADS_DIR",
    )

    jackett_url: str = Field(default="http://jackett:9117", alias="JACKETT_URL")
    jackett_api_key: str = Field(default="", alias="JACKETT_API_KEY")
    jackett_categories: str = Field(
        default="2000,2020,2030,2040,2050",
        alias="JACKETT_CATEGORIES",
    )
    jackett_search_limit: int = Field(default=20, alias="JACKETT_SEARCH_LIMIT")
    jackett_timeout_seconds: float = Field(default=120.0, alias="JACKETT_TIMEOUT_SECONDS")
    jackett_require_russian_audio: bool = Field(
        default=True,
        alias="JACKETT_REQUIRE_RUSSIAN_AUDIO",
    )
    jackett_strict_russian_only: bool = Field(
        default=True,
        alias="JACKETT_STRICT_RUSSIAN_ONLY",
    )
    jackett_exclude_bad_quality: bool = Field(
        default=True,
        alias="JACKETT_EXCLUDE_BAD_QUALITY",
    )

    profile_auth_enabled: bool = Field(default=False, alias="PROFILE_AUTH_ENABLED")
    profile_default_pin: str = Field(default="", alias="PROFILE_DEFAULT_PIN")
    profile_second_pin: str = Field(default="", alias="PROFILE_SECOND_PIN")
    legacy_profile_headers_enabled: bool = Field(default=False, alias="LEGACY_PROFILE_HEADERS_ENABLED")

    registration_enabled: bool = Field(default=True, alias="REGISTRATION_ENABLED")
    registration_invite_code: str = Field(default="", alias="REGISTRATION_INVITE_CODE")
    auth_session_ttl_days: int = Field(default=30, alias="AUTH_SESSION_TTL_DAYS")
    media_stream_token_ttl_minutes: int = Field(default=360, alias="MEDIA_STREAM_TOKEN_TTL_MINUTES")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def enabled_user_search_adapters(self) -> set[str]:
        return {
            item.strip()
            for item in self.user_search_adapters.split(",")
            if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
