from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    IMAGE = "image"  # For jpg, png, etc.


class DocumentAnalysisRequest(BaseModel):
    """Request model for document analysis"""

    file_url: str = Field(..., description="URL or local path to the document file")
    job_description: str = Field(..., description="Job description text")
    required_skills: List[str] = Field(
        default=[], description="List of required skills"
    )
    preferred_skills: List[str] = Field(
        default=[], description="List of preferred skills"
    )
    file_type: FileType = Field(..., description="Type of document file")
    language: str = Field(default="en", description="Document language (en/ar)")
    callback_url: Optional[str] = Field(
        None, description="Webhook URL for async processing"
    )

    class Config:
        schema_extra = {
            "example": {
                "file_url": "/path/to/resume.pdf",
                "job_description": "Looking for a Python developer with 3+ years experience...",
                "required_skills": ["Python", "FastAPI", "SQL"],
                "preferred_skills": ["Docker", "AWS", "React"],
                "file_type": "pdf",
                "language": "en",
                "callback_url": "https://example.com/webhook",
            }
        }


class DocumentBatchAnalysisRequest(BaseModel):
    """Request model for batch document analysis"""

    documents: List[DocumentAnalysisRequest] = Field(
        ..., description="List of documents to analyze"
    )
    job_posting_id: Optional[str] = Field(None, description="ID for grouping analyses")

    class Config:
        schema_extra = {
            "example": {
                "documents": [
                    {
                        "file_url": "/path/to/resume1.pdf",
                        "job_description": "Python Developer position...",
                        "required_skills": ["Python", "FastAPI"],
                        "file_type": "pdf",
                    },
                    {
                        "file_url": "/path/to/resume2.docx",
                        "job_description": "Python Developer position...",
                        "required_skills": ["Python", "FastAPI"],
                        "file_type": "docx",
                    },
                ],
                "job_posting_id": "job_123",
            }
        }


# Keep your existing interview models for reference
class InterviewAnalysisRequest(BaseModel):
    """Existing interview request - keep for reference"""

    audio_url: str
    job_description: str
    questions: Optional[List[str]] = None
    language: str = "en"
    callback_url: Optional[str] = None


# class AsyncProcessQueuedJobs(BaseModel):
#     """Keep this unchanged - it's generic"""
#     max_jobs: int = Field(default=10, ge=1, le=100)
#     job_type: QueuedJobType = QueuedJobType.INTERVIEW  # You might want to add DOCUMENT type


class QueuedJobType(str, Enum):
    PROCESSVIAIDS = "process_via_ids"
    PROCESSALL = "process_all"
    PROCESSVIAUSER = "process_via_user"
    PROCESSVIADATE = "process_via_date"


class AsyncProcessQueuedJobs(BaseModel):
    job_type: QueuedJobType
    user_id: str
    job_ids: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    callback_url: Optional[HttpUrl] = None
