from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.analysis.request import QueuedJobType
from app.models.analysis.response import DocumentAnalysisResult
from app.models.shared.base import ErrorResponse


class JobStatusOptions(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RequestJobsStatus(BaseModel):
    offset: int = Field(..., description="Pagination offset")
    limit: int = Field(..., description="Pagination limit")
    status: JobStatusOptions = Field(
        ..., description="Status of the queued job processing"
    )
    job_ids: Optional[List[str]] = Field(default=None, description="List of job IDs")
    start_date: Optional[datetime] = Field(
        default=None, description="Start date for filtering jobs"
    )
    end_date: Optional[datetime] = Field(
        default=None, description="End date for filtering jobs"
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID for filtering jobs"
    )

    class Config:
        schema_extra = {
            "example": {
                "job_type": "process_via_ids",
                "offset": 0,
                "limit": 10,
                "status": JobStatusOptions.PROCESSING,
                "job_ids": [101, 102, 103],
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
                "user_id": "user_12345",
            }
        }


class JobStatusResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the analysis job")
    status: str = Field(
        ...,
        pattern="^(queued|processing|completed|failed)$",
        description="Current status of the analysis job",
    )
    result_url: Optional[str] = Field(
        default=None, description="URL to retrieve the analysis result if completed"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if the job failed"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "job_123456",
                    "status": "completed",
                    "result_url": "/v1/analysis/job_123456/result",
                    "error_message": None,
                }
            ]
        }
    }


class JobsResultRequest(BaseModel):
    offset: int = Field(..., description="Pagination offset")
    limit: int = Field(..., description="Pagination limit")
    job_ids: Optional[List[str]] = Field(default=None, description="List of job IDs")
    start_date: Optional[datetime] = Field(
        default=None, description="Start date for filtering jobs"
    )
    end_date: Optional[datetime] = Field(
        default=None, description="End date for filtering jobs"
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID for filtering jobs"
    )

    class Config:
        schema_extra = {
            "example": {
                "offset": 0,
                "limit": 10,
                "job_ids": [101, 102, 103],
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
                "user_id": "user_12345",
            }
        }


class JobResultResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the analysis job")
    analysis_result: DocumentAnalysisResult = Field(
        ..., description="Detailed analysis result of the interview"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "job_123456",
                    "analysis_result": {
                        "extracted_text": "John Doe\nSoftware Engineer...",
                        "structured_data": {
                            "name": "John Doe",
                            "email": "john.doe@email.com",
                            "skills": ["Python", "FastAPI", "SQL"],
                        },
                        "overall_score": 82.5,
                        "score_breakdown": {
                            "skills_score": 85.5,
                            "experience_score": 72.0,
                            "education_score": 90.0,
                            "overall_fit": 82.5,
                        },
                        "skills_match": {
                            "required_skills_matched": ["Python", "FastAPI"],
                            "missing_required_skills": ["AWS"],
                            "skill_match_percentage": 66.7,
                        },
                        "key_insights": [
                            "Strong Python and FastAPI experience",
                            "Missing AWS experience which is required",
                            "Excellent educational background",
                        ],
                        "processing_time": 15.2,
                        "confidence_scores": {
                            "name_extraction": 0.95,
                            "skills_extraction": 0.88,
                        },
                    },
                }
            ]
        }
    }


class JobsResultResponse(BaseModel):
    jobs: List[JobResultResponse] = Field(
        ..., description="List of job result responses"
    )
    total_count: int = Field(
        ..., description="Total number of jobs matching the criteria"
    )
    offset: int = Field(description="Pagination offset", default=0)
    limit: int = Field(description="Pagination limit", default=10)
    pages: int = Field(..., description="Total number of pages")
    current_page: int = Field(..., description="Current page number")


class JobsStatusResponse(BaseModel):
    jobs: List[JobStatusResponse] = Field(
        ..., description="List of job status responses"
    )
    total_count: int = Field(
        ..., description="Total number of jobs matching the criteria"
    )
    offset: int = Field(description="Pagination offset", default=0)
    limit: int = Field(description="Pagination limit", default=10)
    pages: int = Field(..., description="Total number of pages")
    current_page: int = Field(..., description="Current page number")


class DocumentJobsResultRequest(BaseModel):
    """Request model for document jobs result with filtering"""

    job_ids: Optional[List[str]] = None
    user_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_score: Optional[float] = Field(None, ge=0, le=100)
    max_score: Optional[float] = Field(None, ge=0, le=100)
    file_type: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class DocumentJobsResultResponse(BaseModel):
    """Response model for document jobs result"""

    jobs: List["DocumentAnalysisResult"]  # Your DocumentAnalysisResult model
    total_count: int
    offset: int
    limit: int
    pages: int
    current_page: int
