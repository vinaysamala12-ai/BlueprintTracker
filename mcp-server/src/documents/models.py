"""Pydantic I/O models for the documents domain."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Input models ─────────────────────────────────────────────────────────────

class ListDocumentsParams(BaseModel):
    status: Optional[str] = Field(
        None,
        description="Filter by status: pending | in_review | approved | rejected",
    )
    search: Optional[str] = Field(None, description="Search documents by name")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    limit: int = Field(20, ge=1, le=100, description="Results per page")


class GetDocumentParams(BaseModel):
    document_id: str = Field(..., description="MongoDB ObjectId of the document")


class Stakeholder(BaseModel):
    name: str = Field(..., description="Stakeholder full name")
    email: str = Field(..., description="Stakeholder email address")


class ReminderConfig(BaseModel):
    intervalHours: int = Field(24, ge=1, description="Hours between reminders")
    maxReminders: int = Field(3, ge=1, description="Maximum number of reminders to send")


class SubmitDocumentParams(BaseModel):
    name: str = Field(..., description="Document name / title")
    storageType: str = Field(
        ...,
        description="Storage location: sharepoint | onedrive | external",
    )
    submittedBy: str = Field(..., description="Name of the person submitting")
    submittedByEmail: str = Field(..., description="Email of the submitter (for completion notifications)")
    stakeholders: List[Stakeholder] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly 3 stakeholders who must approve the document",
    )
    webUrl: Optional[str] = Field(None, description="Direct URL to the document (for external or storage links)")
    fileId: Optional[str] = Field(None, description="File ID in OneDrive/SharePoint")
    driveId: Optional[str] = Field(None, description="Drive ID in OneDrive/SharePoint")
    siteId: Optional[str] = Field(None, description="SharePoint site ID")
    path: Optional[str] = Field("/", description="Folder path within storage")
    mimeType: Optional[str] = Field(None, description="MIME type of the file")
    fileSize: Optional[int] = Field(None, description="File size in bytes")
    reminderConfig: Optional[ReminderConfig] = Field(
        None,
        description="Reminder schedule (defaults: intervalHours=24, maxReminders=3)",
    )
    notes: Optional[str] = Field(None, description="Notes or instructions for approvers")


class DeleteDocumentParams(BaseModel):
    document_id: str = Field(..., description="MongoDB ObjectId of the document to delete")


# ── Output models ─────────────────────────────────────────────────────────────

class DocumentItem(BaseModel):
    id: str
    name: str
    path: str
    storageType: str
    status: str
    submittedBy: str
    submittedByEmail: Optional[str] = None
    webUrl: Optional[str] = None
    fileSize: Optional[int] = None
    mimeType: Optional[str] = None
    approvalRequestId: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class ListDocumentsResult(BaseModel):
    documents: List[Dict[str, Any]]
    total: int
    page: int
    limit: int
    pages: int


class DocumentStatsResult(BaseModel):
    total: int
    pending: int
    in_review: int
    approved: int
    rejected: int


class SubmitDocumentResult(BaseModel):
    message: str
    document: Dict[str, Any]
    approvalRequest: Optional[Dict[str, Any]] = None


class DeleteDocumentResult(BaseModel):
    message: str
    document_id: str


class NoParams(BaseModel):
    """Empty params model for tools that require no input."""
