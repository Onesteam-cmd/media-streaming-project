from pydantic import BaseModel, Field


class TransmissionTorrentAddRequest(BaseModel):
    filename: str = Field(min_length=1)
    download_dir: str | None = None
