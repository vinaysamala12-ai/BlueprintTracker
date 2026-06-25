"""Business logic for the documents domain — all calls go to the BlueprintTracker API."""

from typing import Any, Dict

from framework import get_shared_http_client
from src.shared.client import get_blueprint_api_url, get_blueprint_headers

from .models import (
    DeleteDocumentResult,
    DocumentStatsResult,
    ListDocumentsResult,
    SubmitDocumentResult,
)


async def list_documents(
    status: str | None,
    search: str | None,
    page: int,
    limit: int,
) -> ListDocumentsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    params: Dict[str, Any] = {"page": page, "limit": limit}
    if status:
        params["status"] = status
    if search:
        params["search"] = search

    response = await client.get(
        f"{get_blueprint_api_url()}/api/documents",
        headers=headers,
        params=params,
    )
    response.raise_for_status()
    data = response.json()
    return ListDocumentsResult(
        documents=data.get("documents", []),
        total=data.get("total", 0),
        page=data.get("page", page),
        limit=data.get("limit", limit),
        pages=data.get("pages", 1),
    )


async def get_document(document_id: str) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/documents/{document_id}",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


async def submit_document(payload: Dict[str, Any]) -> SubmitDocumentResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.post(
        f"{get_blueprint_api_url()}/api/documents/submit",
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    return SubmitDocumentResult(
        message=data.get("message", "Document submitted"),
        document=data.get("document", {}),
        approvalRequest=data.get("approvalRequest"),
    )


async def delete_document(document_id: str) -> DeleteDocumentResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.delete(
        f"{get_blueprint_api_url()}/api/documents/{document_id}",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return DeleteDocumentResult(
        message=data.get("message", "Document deleted"),
        document_id=document_id,
    )


async def get_document_stats() -> DocumentStatsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/documents/stats",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return DocumentStatsResult(
        total=data.get("total", 0),
        pending=data.get("pending", 0),
        in_review=data.get("in_review", 0),
        approved=data.get("approved", 0),
        rejected=data.get("rejected", 0),
    )
