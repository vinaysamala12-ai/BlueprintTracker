"""Business logic for the approvals domain — all calls go to the BlueprintTracker API."""

from typing import Any, Dict

from framework import get_shared_http_client
from src.shared.client import get_blueprint_api_url, get_blueprint_headers

from .models import (
    ApprovalStatsResult,
    ListApprovalsResult,
    LogsResult,
    RunSchedulerResult,
    SchedulerStatusResult,
    SendReminderResult,
    ToggleRemindersResult,
)


async def list_approvals(
    status: str | None,
    search: str | None,
    page: int,
    limit: int,
) -> ListApprovalsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    params: Dict[str, Any] = {"page": page, "limit": limit}
    if status:
        params["status"] = status
    if search:
        params["search"] = search

    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals",
        headers=headers,
        params=params,
    )
    response.raise_for_status()
    data = response.json()
    return ListApprovalsResult(
        approvals=data.get("approvals", []),
        total=data.get("total", 0),
        page=data.get("page", page),
        limit=data.get("limit", limit),
        pages=data.get("pages", 1),
    )


async def get_approval(approval_id: str) -> Dict[str, Any]:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals/{approval_id}",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


async def get_approval_stats() -> ApprovalStatsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals/stats",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return ApprovalStatsResult(
        total=data.get("total", 0),
        pending=data.get("pending", 0),
        in_progress=data.get("in_progress", 0),
        approved=data.get("approved", 0),
        rejected=data.get("rejected", 0),
        reminders_sent=data.get("reminders_sent"),
    )


async def send_reminder(approval_id: str) -> SendReminderResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.post(
        f"{get_blueprint_api_url()}/api/approvals/{approval_id}/remind",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return SendReminderResult(
        message=data.get("message", "Reminders sent"),
        reminders_sent=data.get("reminders_sent", 0),
    )


async def toggle_reminders(approval_id: str, enabled: bool) -> ToggleRemindersResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.patch(
        f"{get_blueprint_api_url()}/api/approvals/{approval_id}/reminders",
        headers=headers,
        json={"enabled": enabled},
    )
    response.raise_for_status()
    data = response.json()
    return ToggleRemindersResult(
        message=data.get("message", "Reminder setting updated"),
        approval_id=approval_id,
        reminders_enabled=enabled,
    )


async def get_approval_logs(approval_id: str) -> LogsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals/{approval_id}/logs",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    logs = data if isinstance(data, list) else data.get("logs", [])
    return LogsResult(logs=logs, total=len(logs))


async def get_all_notification_logs(page: int, limit: int) -> LogsResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals/logs/all",
        headers=headers,
        params={"page": page, "limit": limit},
    )
    response.raise_for_status()
    data = response.json()
    return LogsResult(
        logs=data.get("logs", []),
        total=data.get("total", 0),
        page=data.get("page", page),
        pages=data.get("pages", 1),
    )


async def get_scheduler_status() -> SchedulerStatusResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.get(
        f"{get_blueprint_api_url()}/api/approvals/scheduler/status",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return SchedulerStatusResult(
        running=data.get("running", False),
        enabled=data.get("enabled", False),
        last_run=data.get("lastRun") or data.get("last_run"),
        next_run=data.get("nextRun") or data.get("next_run"),
    )


async def run_scheduler() -> RunSchedulerResult:
    client = get_shared_http_client()
    headers = await get_blueprint_headers()
    response = await client.post(
        f"{get_blueprint_api_url()}/api/approvals/scheduler/run",
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return RunSchedulerResult(
        message=data.get("message", "Scheduler run complete"),
        reminders_sent=data.get("remindersSent") or data.get("reminders_sent"),
        requests_processed=data.get("requestsProcessed") or data.get("requests_processed"),
    )
