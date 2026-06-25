"""Configuration domain tool registrations."""

from typing import Any, Dict
from pydantic import BaseModel
from framework import register_tool

from .models import TestEmailParams, UpdateConfigParams
from .tools import get_config, test_email, update_config


class NoParams(BaseModel):
    """Empty params model for tools that require no input."""


@register_tool("get_configuration")
async def get_configuration_tool(params: NoParams) -> Dict[str, Any]:
    """
    Get the current BlueprintTracker system configuration.

    Returns all configuration sections: MS365 email settings, reminder scheduler
    settings, storage (OneDrive/SharePoint) settings, and the app URL.
    Secrets (clientSecret, etc.) are masked with bullet characters.
    """
    return await get_config()


@register_tool("update_configuration")
async def update_configuration_tool(params: UpdateConfigParams) -> Dict[str, Any]:
    """
    Update BlueprintTracker system configuration.

    Saves one or more configuration sections: MS365 email (tenantId, clientId,
    clientSecret, fromEmail), scheduler (enabled, cronExpression, reminderIntervalHours,
    maxReminders), storage (type, credentials, driveId, folderPath), and appUrl.
    If the cron expression changes the scheduler restarts automatically.
    Only provide sections you want to update — omitted sections are unchanged.
    """
    payload: Dict[str, Any] = {}
    if params.ms365 is not None:
        payload["ms365"] = {k: v for k, v in params.ms365.model_dump().items() if v is not None}
    if params.scheduler is not None:
        payload["scheduler"] = {k: v for k, v in params.scheduler.model_dump().items() if v is not None}
    if params.storage is not None:
        payload["storage"] = {k: v for k, v in params.storage.model_dump().items() if v is not None}
    if params.appUrl is not None:
        payload["appUrl"] = params.appUrl
    return await update_config(payload)


@register_tool("test_email", timeout_seconds=30)
async def test_email_tool(params: TestEmailParams) -> Dict[str, Any]:
    """
    Send a test email to verify Microsoft 365 email credentials.

    Attempts to send a test message to the specified address using the
    currently configured MS365 tenant, client, and from-email settings.
    Useful for validating configuration before going live.
    Returns success status or an error message with details.
    """
    return await test_email(params.to_email)
