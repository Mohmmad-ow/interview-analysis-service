from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class AuditLogEntry(BaseModel):
    """Single audit log entry response"""

    id: int = Field(..., description="Unique log entry ID")
    timestamp: datetime = Field(..., description="When the action occurred")
    user_id: str = Field(..., description="User who performed the action")
    action: str = Field(..., description="Type of action performed")
    resource: Optional[str] = Field(None, description="Resource affected by the action")
    success: bool = Field(..., description="Whether the action succeeded")
    processing_time: Optional[float] = Field(
        None, description="How long the action took"
    )
    error_type: Optional[str] = Field(None, description="Type of error if failed")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )

    class Config:
        schema_extra = {
            "example": {
                "id": 12345,
                "timestamp": "2024-01-15T10:30:00Z",
                "user_id": "user_123",
                "action": "analysis_completed",
                "resource": "interview/job_abc123",
                "success": True,
                "processing_time": 45.2,
                "metadata": {
                    "audio_duration": 120.5,
                    "audio_url": "https://example.com/interview.mp3",
                    "technical_score": 8.5,
                },
            }
        }


class ErrorLogEntry(BaseModel):
    """Single error log entry response"""

    id: int = Field(..., description="Unique error log ID")
    timestamp: datetime = Field(..., description="When the error occurred")
    user_id: Optional[str] = Field(None, description="User who encountered the error")
    job_id: Optional[str] = Field(None, description="Related job ID if applicable")
    error_type: str = Field(..., description="Category of error")
    error_message: str = Field(..., description="Human-readable error message")
    stack_trace: Optional[str] = Field(
        None, description="Full stack trace for debugging"
    )
    request_data: Optional[Dict[str, Any]] = Field(
        None, description="Request data that caused error"
    )
    resolved: bool = Field(..., description="Whether the error has been resolved")
    resolved_at: Optional[datetime] = Field(
        None, description="When the error was resolved"
    )

    class Config:
        schema_extra = {
            "example": {
                "id": 67890,
                "timestamp": "2024-01-15T10:25:00Z",
                "user_id": "user_123",
                "job_id": "job_abc123",
                "error_type": "transcription_failed",
                "error_message": "Audio file could not be processed",
                "resolved": False,
                "request_data": {
                    "audio_url": "https://example.com/corrupted.mp3",
                    "language": "en",
                },
            }
        }


class PaginatedAuditLogs(BaseModel):
    """Paginated response for audit logs"""

    items: List[AuditLogEntry] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching records")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_previous: bool = Field(..., description="Whether there are previous pages")

    class Config:
        schema_extra = {
            "example": {
                "items": [],
                "total": 150,
                "page": 1,
                "page_size": 50,
                "total_pages": 3,
                "has_next": True,
                "has_previous": False,
            }
        }


class PaginatedErrorLogs(BaseModel):
    """Paginated response for error logs"""

    items: List[ErrorLogEntry] = Field(..., description="List of error log entries")
    total: int = Field(..., description="Total number of matching records")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


class AuditStatsResponse(BaseModel):
    """Statistics response for audit data"""

    time_range: str = Field(..., description="The time range these stats cover")
    total_actions: int = Field(..., description="Total number of actions")
    success_rate: float = Field(..., description="Percentage of successful actions")
    average_processing_time: float = Field(..., description="Average time per action")
    actions_by_type: Dict[str, int] = Field(..., description="Count of actions by type")
    top_users: List[Dict[str, Any]] = Field(..., description="Most active users")

    class Config:
        schema_extra = {
            "example": {
                "time_range": "last_7_days",
                "total_actions": 1245,
                "success_rate": 0.89,
                "average_processing_time": 32.1,
                "actions_by_type": {
                    "analysis_started": 450,
                    "analysis_completed": 400,
                    "analysis_failed": 50,
                    "user_login": 345,
                },
                "top_users": [
                    {"user_id": "user_123", "action_count": 234},
                    {"user_id": "user_456", "action_count": 198},
                ],
            }
        }
