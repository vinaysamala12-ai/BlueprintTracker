"""Business logic for the storage domain."""

from typing import Any, Dict, Optional

from framework import get_shared_http_client
from src.shared.client import get_blueprint_api_url, get_blueprint_headers


async def list_storage_files(folder: Optional[str]) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    params: Dict[str, Any] = {}
    if folder:
        params["folder"] = folder
    response = await client.get(
        f"{get_blueprint_api_url()}/api/storage/files",
        headers=headers,
        params=params,
    )
    response.raise_for_status()
    return response.json()


async def get_storage_file(drive_id: str, file_id: str) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/storage/file/{drive_id}/{file_id}",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


async def test_storage_connection() -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.post(
        f"{get_blueprint_api_url()}/api/storage/test",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()
