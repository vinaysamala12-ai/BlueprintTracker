"""Pydantic I/O models for the configuration domain."""

from typing import Optional
from pydantic import BaseModel, Field


# ── Input models ─────────────────────────────────────────────────────────────

class Ms365Config(BaseModel):
    tenantId: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    fromEmail: Optional[str] = None
    fromName: Optional[str] = None


class SchedulerConfig(BaseModel):
    enabled: Optional[bool] = None
    cronExpression: Optional[str] = None
    reminderIntervalHours: Optional[int] = None
    maxReminders: Optional[int] = None


class StorageConfig(BaseModel):
    type: Optional[str] = Field(None, description="sharepoint or onedrive")
    tenantId: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    driveId: Optional[str] = None
    siteUrl: Optional[str] = None
    folderPath: Optional[str] = None


class UpdateConfigParams(BaseModel):
    ms365: Optional[Ms365Config] = Field(None, description="Microsoft 365 email settings")
    scheduler: Optional[SchedulerConfig] = Field(None, description="Reminder scheduler settings")
    storage: Optional[StorageConfig] = Field(None, description="OneDrive/SharePoint storage settings")
    appUrl: Optional[str] = Field(None, description="Public app URL used in email links")


class TestEmailParams(BaseModel):
    to_email: str = Field(..., description="Email address to send the test message to")
