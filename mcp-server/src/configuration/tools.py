"""Business logic for the configuration domain."""

from typing import Any, Dict

from framework import get_shared_http_client
from src.shared.client import get_blueprint_api_url, get_blueprint_headers


async def get_config() -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/config",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.put(
        f"{get_blueprint_api_url()}/api/config",
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    return response.json()


async def test_email(to_email: str) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.post(
        f"{get_blueprint_api_url()}/api/config/test-email",
        headers=headers,
        json={"toEmail": to_email},
    )
    response.raise_for_status()
    return response.json()
