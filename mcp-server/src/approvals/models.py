"""Pydantic I/O models for the approvals domain."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Input models ─────────────────────────────────────────────────────────────

class ListApprovalsParams(BaseModel):
    status: Optional[str] = Field(
        None,
        description="Filter by status: pending | in_progress | approved | rejected",
    )
    search: Optional[str] = Field(None, description="Search by document name")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    limit: int = Field(20, ge=1, le=100, description="Results per page")


class GetApprovalParams(BaseModel):
    approval_id: str = Field(..., description="MongoDB ObjectId of the approval request")


class SendReminderParams(BaseModel):
    approval_id: str = Field(..., description="MongoDB ObjectId of the approval request")


class ToggleRemindersParams(BaseModel):
    approval_id: str = Field(..., description="MongoDB ObjectId of the approval request")
    enabled: bool = Field(..., description="True to enable automatic reminders, False to disable")


class GetApprovalLogsParams(BaseModel):
    approval_id: str = Field(..., description="MongoDB ObjectId of the approval request")


class GetAllLogsParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number (1-based)")
    limit: int = Field(50, ge=1, le=200, description="Results per page")


# ── Output models ─────────────────────────────────────────────────────────────

class ListApprovalsResult(BaseModel):
    approvals: List[Dict[str, Any]]
    total: int
    page: int
    limit: int
    pages: int


class ApprovalStatsResult(BaseModel):
    total: int
    pending: int
    in_progress: int
    approved: int
    rejected: int
    reminders_sent: Optional[int] = None


class SendReminderResult(BaseModel):
    message: str
    reminders_sent: int


class ToggleRemindersResult(BaseModel):
    message: str
    approval_id: str
    reminders_enabled: bool


class LogsResult(BaseModel):
    logs: List[Dict[str, Any]]
    total: int
    page: Optional[int] = None
    pages: Optional[int] = None


class SchedulerStatusResult(BaseModel):
    running: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool


class RunSchedulerResult(BaseModel):
    message: str
    reminders_sent: Optional[int] = None
    requests_processed: Optional[int] = None


class NoParams(BaseModel):
    """Empty params model for tools that require no input."""
