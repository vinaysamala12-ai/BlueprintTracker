"""Document domain tool registrations."""

from typing import Any, Dict
from framework import register_tool

from .models import (
    DeleteDocumentParams,
    GetDocumentParams,
    ListDocumentsParams,
    NoParams,
    SubmitDocumentParams,
)
from .tools import (
    delete_document,
    get_document,
    get_document_stats,
    list_documents,
    submit_document,
)


@register_tool("list_documents")
async def list_documents_tool(params: ListDocumentsParams) -> Dict[str, Any]:
    """
    List documents in BlueprintTracker with optional filtering and pagination.

    Returns a paginated list of documents. Filter by status (pending, in_review,
    approved, rejected) or search by document name. Each document includes its
    storage location, status, submitter info, and linked approval request ID.
    """
    result = await list_documents(
        status=params.status,
        search=params.search,
        page=params.page,
        limit=params.limit,
    )
    return result.model_dump()


@register_tool("get_document")
async def get_document_tool(params: GetDocumentParams) -> Dict[str, Any]:
    """
    Retrieve a single document by its ID.

    Returns full document details including status, storage metadata, submitter
    information, and the linked approval request ID if one exists.
    """
    result = await get_document(params.document_id)
    return result


@register_tool("submit_document", timeout_seconds=30)
async def submit_document_tool(params: SubmitDocumentParams) -> Dict[str, Any]:
    """
    Submit a document for approval by exactly 3 stakeholders.

    Creates a Document record and triggers an ApprovalRequest workflow.
    Sends initial approval request emails to all 3 stakeholders immediately.
    Each stakeholder receives a unique link to approve or reject the document.
    Returns the created document and approval request details.
    """
    payload: Dict[str, Any] = {
        "name": params.name,
        "storageType": params.storageType,
        "submittedBy": params.submittedBy,
        "submittedByEmail": params.submittedByEmail,
        "stakeholders": [s.model_dump() for s in params.stakeholders],
    }
    if params.webUrl is not None:
        payload["webUrl"] = params.webUrl
    if params.fileId is not None:
        payload["fileId"] = params.fileId
    if params.driveId is not None:
        payload["driveId"] = params.driveId
    if params.siteId is not None:
        payload["siteId"] = params.siteId
    if params.path is not None:
        payload["path"] = params.path
    if params.mimeType is not None:
        payload["mimeType"] = params.mimeType
    if params.fileSize is not None:
        payload["fileSize"] = params.fileSize
    if params.reminderConfig is not None:
        payload["reminderConfig"] = params.reminderConfig.model_dump()
    if params.notes is not None:
        payload["notes"] = params.notes

    result = await submit_document(payload)
    return result.model_dump()


@register_tool("delete_document")
async def delete_document_tool(params: DeleteDocumentParams) -> Dict[str, Any]:
    """
    Delete a document and its associated approval request.

    Permanently removes the document record and cascades to delete the linked
    ApprovalRequest (and its stakeholder tokens). This action cannot be undone.
    """
    result = await delete_document(params.document_id)
    return result.model_dump()


@register_tool("get_document_stats")
async def get_document_stats_tool(params: NoParams) -> Dict[str, Any]:
    """
    Get aggregated document counts grouped by status.

    Returns total document count plus breakdown by status:
    pending, in_review, approved, and rejected. Useful for dashboard summaries.
    """
    result = await get_document_stats()
    return result.model_dump()
