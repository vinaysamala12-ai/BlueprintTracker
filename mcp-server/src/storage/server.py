"""Storage domain tool registrations."""

from typing import Any, Dict
from pydantic import BaseModel
from framework import register_tool

from .models import GetStorageFileParams, ListStorageFilesParams
from .tools import get_storage_file, list_storage_files, test_storage_connection


class NoParams(BaseModel):
    """Empty params model for tools that require no input."""


@register_tool("list_storage_files")
async def list_storage_files_tool(params: ListStorageFilesParams) -> Dict[str, Any]:
    """
    List files in the configured OneDrive or SharePoint storage location.

    Browses the storage folder configured in Settings. Optionally pass a
    sub-folder path to navigate into it. Returns file names, sizes, MIME types,
    IDs, and web URLs that can be used when submitting documents for approval.
    """
    return await list_storage_files(params.folder)


@register_tool("get_storage_file")
async def get_storage_file_tool(params: GetStorageFileParams) -> Dict[str, Any]:
    """
    Get metadata for a specific file in OneDrive or SharePoint by its IDs.

    Returns the file's name, size, MIME type, web URL, creation and
    modification timestamps. The driveId and fileId are returned by
    list_storage_files and can be used in submit_document.
    """
    return await get_storage_file(params.drive_id, params.file_id)


@register_tool("test_storage_connection", timeout_seconds=30)
async def test_storage_connection_tool(params: NoParams) -> Dict[str, Any]:
    """
    Test the OneDrive/SharePoint storage connection with the current credentials.

    Attempts to authenticate and list the root folder using the storage
    credentials configured in Settings. Returns success/failure and any
    error details to help diagnose credential or permission issues.
    """
    return await test_storage_connection()
