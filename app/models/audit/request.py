from os import error
from time import timezone
from annotated_types import Timezone
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import JSON


class AuditAction(str, Enum):
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_FAILED = "analysis_failed"
    JOB_CREATED = "job_created"
    JOB_STATUS_CHANGED = "job_status_changed"
    USER_LOGIN = "user_login"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class AuditTimeRange(str, Enum):
    LAST_HOUR = "last_hour"
    LAST_24_HOURS = "last_24_hours"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    CUSTOM = "custom"


class AuditLogFilter(BaseModel):
    """Request model for filtering audit logs"""

    user_ids: Optional[List[str]] = Field(
        default=None, description="Filter by specific users"
    )
    actions: Optional[List[AuditAction]] = Field(
        default=None, description="Filter by action types"
    )
    success_only: Optional[bool] = Field(
        default=None, description="Only successful actions"
    )
    time_range: AuditTimeRange = Field(
        default=AuditTimeRange.LAST_24_HOURS, description="Predefined time ranges"
    )
    start_date: Optional[datetime] = Field(
        default=None, description="Custom start date (requires time_range='custom')"
    )
    end_date: Optional[datetime] = Field(
        default=None, description="Custom end date (requires time_range='custom')"
    )
    resource_pattern: Optional[str] = Field(
        default=None, description="LIKE pattern for resource field"
    )
    page: int = Field(default=1, ge=1, description="Page number for pagination")
    page_size: int = Field(
        default=50, ge=1, le=1000, description="Number of records per page"
    )

    class Config:
        schema_extra = {
            "example": {
                "user_ids": ["user_123", "user_456"],
                "actions": ["analysis_started", "analysis_completed"],
                "success_only": True,
                "time_range": "last_7_days",
                "page": 1,
                "page_size": 100,
            }
        }


class AuditLog(BaseModel):
    user_id: Optional[str] = Field(default=None, description="Filter by specific users")
    action: Optional[AuditAction] = Field(
        default=None, description="Filter by action types"
    )
    success_only: Optional[bool] = Field(
        default=None, description="Only successful actions"
    )
    timestamp: datetime = Field(
        description="time of audit creation", default=datetime.now(UTC)
    )
    resource_pattern: Optional[str] = Field(
        default=None, description="LIKE pattern for resource field"
    )
    processing_time: Optional[float] = Field(
        default=None, description="Processing time in seconds"
    )
    error_type: Optional[str] = Field(
        default=None, description="Type of error if applicable"
    )
    metadata: Optional[dict] = Field(
        default=None, description="Additional information as key-value pairs"
    )


class ErrorLogFilter(BaseModel):
    """Request model for filtering error logs"""

    error_types: Optional[List[str]] = Field(
        default=None, description="Filter by error types"
    )
    user_ids: Optional[List[str]] = Field(
        default=None, description="Filter by users who encountered errors"
    )
    job_ids: Optional[List[str]] = Field(
        default=None, description="Filter by specific job IDs"
    )
    resolved_only: Optional[bool] = Field(
        default=None, description="Only resolved errors"
    )
    unresolved_only: Optional[bool] = Field(
        default=None, description="Only unresolved errors"
    )
    start_date: Optional[datetime] = Field(default=None)
    end_date: Optional[datetime] = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
