"""BlueprintTracker API client with token caching.

Each tool calls ``get_blueprint_headers()`` to get the Authorization header
for requests to the BlueprintTracker backend. The JWT is fetched once and
reused for 23 hours before refreshing.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx

_token: Optional[str] = None
_expires_at: Optional[datetime] = None


def get_blueprint_api_url() -> str:
    url = os.getenv("BLUEPRINT_API_URL", "http://localhost:5000").rstrip("/")
    return url


async def get_blueprint_headers() -> Dict[str, str]:
    """Return headers with a valid Bearer JWT for the BlueprintTracker API."""
    global _token, _expires_at

    now = datetime.utcnow()
    if _token and _expires_at and now < _expires_at:
        return {"Authorization": f"Bearer {_token}"}

    username = os.getenv("BLUEPRINT_USERNAME", "admin")
    password = os.getenv("BLUEPRINT_PASSWORD", "")
    base_url = get_blueprint_api_url()

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base_url}/api/auth/login",
            json={"username": username, "password": password},
        )
        response.raise_for_status()
        data = response.json()

    _token = data["token"]
    _expires_at = now + timedelta(hours=23)
    return {"Authorization": f"Bearer {_token}"}
