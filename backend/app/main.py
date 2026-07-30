from contextlib import asynccontextmanager
import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.adapters import router as adapters_router
from app.api.auth import router as auth_router
from app.api.candidates import router as candidates_router
from app.api.configuration import router as configuration_router
from app.api.jellyfin import router as jellyfin_router
from app.api.media import router as media_router
from app.api.readiness import router as readiness_router
from app.api.requests import router as requests_router
from app.api.search import router as search_router
from app.api.system import router as system_router
from app.api.transmission import router as transmission_router
from app.api.watch_positions import router as watch_positions_router
from app.core.config import get_settings
from app.db.init_db import init_db


settings = get_settings()

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/ogg", ".ogv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("video/quicktime", ".mov")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(adapters_router)
app.include_router(search_router)
app.include_router(requests_router)
app.include_router(candidates_router)
app.include_router(system_router)
app.include_router(jellyfin_router)
app.include_router(transmission_router)
app.include_router(readiness_router)
app.include_router(configuration_router)
app.include_router(media_router)
app.include_router(watch_positions_router)

app.mount(
    "/media-files",
    StaticFiles(directory=settings.media_root),
    name="media-files",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": settings.project_name,
        "timezone": settings.timezone,
        "active_adapter": settings.ingest_adapter,
    }
