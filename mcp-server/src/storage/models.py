"""Pydantic I/O models for the storage domain."""

from typing import Optional
from pydantic import BaseModel, Field


class ListStorageFilesParams(BaseModel):
    folder: Optional[str] = Field(
        None,
        description="Folder path to browse (defaults to root configured in storage settings)",
    )


class GetStorageFileParams(BaseModel):
    drive_id: str = Field(..., description="OneDrive/SharePoint drive ID")
    file_id: str = Field(..., description="File ID within the drive")
