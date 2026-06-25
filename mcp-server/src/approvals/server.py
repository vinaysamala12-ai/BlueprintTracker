"""Approvals domain tool registrations."""

from typing import Any, Dict
from framework import register_tool

from .models import (
    GetAllLogsParams,
    GetApprovalLogsParams,
    GetApprovalParams,
    ListApprovalsParams,
    NoParams,
    SendReminderParams,
    ToggleRemindersParams,
)
from .tools import (
    get_all_notification_logs,
    get_approval,
    get_approval_logs,
    get_approval_stats,
    get_scheduler_status,
    list_approvals,
    run_scheduler,
    send_reminder,
    toggle_reminders,
)


@register_tool("list_approvals")
async def list_approvals_tool(params: ListApprovalsParams) -> Dict[str, Any]:
    """
    List approval requests with optional filtering and pagination.

    Returns paginated approval requests. Filter by status (pending, in_progress,
    approved, rejected) or search by document name. Each result includes the
    document name, overall status, stakeholder breakdown, and progress.
    """
    result = await list_approvals(
        status=params.status,
        search=params.search,
        page=params.page,
        limit=params.limit,
    )
    return result.model_dump()


@register_tool("get_approval")
async def get_approval_tool(params: GetApprovalParams) -> Dict[str, Any]:
    """
    Get full details of a single approval request by ID.

    Returns the complete approval request including all stakeholder statuses,
    their response timestamps, comments, reminder counts, and notification history.
    """
    return await get_approval(params.approval_id)


@register_tool("get_approval_stats")
async def get_approval_stats_tool(params: NoParams) -> Dict[str, Any]:
    """
    Get aggregated approval request counts grouped by status.

    Returns total requests and breakdown by status: pending, in_progress,
    approved, rejected, and total reminders sent. Useful for dashboard summaries.
    """
    result = await get_approval_stats()
    return result.model_dump()


@register_tool("send_reminder", timeout_seconds=30)
async def send_reminder_tool(params: SendReminderParams) -> Dict[str, Any]:
    """
    Manually send reminder emails to pending stakeholders on an approval request.

    Triggers immediate reminder emails to all stakeholders who have not yet
    responded. Respects the reminder interval and max-reminders limits — if a
    stakeholder was reminded recently or has hit the cap, they are skipped.
    Returns how many reminders were sent.
    """
    result = await send_reminder(params.approval_id)
    return result.model_dump()


@register_tool("toggle_reminders")
async def toggle_reminders_tool(params: ToggleRemindersParams) -> Dict[str, Any]:
    """
    Enable or disable automatic scheduled reminders for an approval request.

    When disabled, the cron scheduler skips this request entirely. Manual
    reminders via send_reminder still work regardless of this setting.
    """
    result = await toggle_reminders(params.approval_id, params.enabled)
    return result.model_dump()


@register_tool("get_approval_logs")
async def get_approval_logs_tool(params: GetApprovalLogsParams) -> Dict[str, Any]:
    """
    Get the notification log for a specific approval request.

    Returns all emails sent for this request: initial approval requests,
    reminders, and completion notifications. Each log entry includes
    recipient, email type, status (sent/failed), and timestamp.
    """
    result = await get_approval_logs(params.approval_id)
    return result.model_dump()


@register_tool("get_all_notification_logs")
async def get_all_notification_logs_tool(params: GetAllLogsParams) -> Dict[str, Any]:
    """
    Get all system notification logs with pagination.

    Returns a paginated list of every email sent by the system across all
    approval requests. Includes document name, recipient, email type
    (approval_request, reminder, approved_notify, rejected_notify, test),
    provider (ms365), send status, and any error messages.
    """
    result = await get_all_notification_logs(params.page, params.limit)
    return result.model_dump()


@register_tool("get_scheduler_status")
async def get_scheduler_status_tool(params: NoParams) -> Dict[str, Any]:
    """
    Get the current status of the reminder scheduler.

    Returns whether the scheduler is running, enabled, and when it last ran
    and is next scheduled to run. Useful for diagnosing reminder delivery issues.
    """
    result = await get_scheduler_status()
    return result.model_dump()


@register_tool("run_scheduler", timeout_seconds=60)
async def run_scheduler_tool(params: NoParams) -> Dict[str, Any]:
    """
    Manually trigger the reminder scheduler to run immediately.

    Processes all in-progress approval requests and sends reminders to pending
    stakeholders who are due for a reminder (based on intervalHours and
    maxReminders config). Returns the number of reminders sent and requests processed.
    """
    result = await run_scheduler()
    return result.model_dump()
