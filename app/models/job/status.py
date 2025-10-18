from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from app.models.analysis.response import AnalysisResult
from app.models.shared.base import ErrorResponse


class JobStatusOptions(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the analysis job")
    status: JobStatusOptions = Field(
        ...,
        description="Current status of the analysis job",
    )
    result_url: Optional[str] = Field(
        default=None,
        description="URL to retrieve results if job is completed",
    )
    error: Optional[ErrorResponse] = Field(
        default=None, description="Error details if job failed"
    )
    submitted_at: datetime = Field(..., description="Timestamp when job was submitted")
    completed_at: Optional[datetime] = Field(
        default=None, description="Timestamp when job was completed"
    )

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_123456",
                "status": JobStatusOptions.PROCESSING,
                "result_url": None,
                "error": None,
                "submitted_at": "2023-10-01T12:00:00Z",
                "completed_at": None,
            }
        }


class JobResult(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the analysis job")
    analysis_result: AnalysisResult = Field(
        ..., description="Detailed analysis results"
    )
