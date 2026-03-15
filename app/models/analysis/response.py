from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class StructuredResumeData(BaseModel):
    """Structured data extracted from resume"""

    name: Optional[str] = Field(None, description="Candidate name")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    education: List[Dict[str, Any]] = Field(default=[], description="Education history")
    work_experience: List[Dict[str, Any]] = Field(
        default=[], description="Work experience"
    )
    skills: List[str] = Field(default=[], description="List of skills")
    certifications: List[str] = Field(default=[], description="Certifications")
    languages: List[str] = Field(default=[], description="Languages spoken")
    summary: Optional[str] = Field(None, description="Professional summary")

    class Config:
        schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john.doe@email.com",
                "phone": "+1234567890",
                "education": [
                    {
                        "institution": "University of Example",
                        "degree": "Bachelor of Science in Computer Science",
                        "years": "2018-2022",
                        "gpa": "3.8",
                    }
                ],
                "work_experience": [
                    {
                        "company": "Tech Corp",
                        "title": "Software Engineer",
                        "years": "2022-Present",
                        "description": "Developed web applications using Python and FastAPI",
                    }
                ],
                "skills": ["Python", "FastAPI", "SQL", "Docker"],
                "certifications": ["AWS Certified Developer"],
                "languages": ["English", "Arabic"],
                "summary": "Experienced software engineer with 3+ years in web development",
            }
        }


class ScoreBreakdown(BaseModel):
    """Detailed scoring breakdown"""

    skills_score: float = Field(..., ge=0, le=100, description="Skills matching score")
    experience_score: float = Field(
        ..., ge=0, le=100, description="Experience relevance score"
    )
    education_score: float = Field(
        ..., ge=0, le=100, description="Education matching score"
    )
    overall_fit: float = Field(..., ge=0, le=100, description="Overall fit score")

    class Config:
        schema_extra = {
            "example": {
                "skills_score": 85.5,
                "experience_score": 72.0,
                "education_score": 90.0,
                "overall_fit": 82.5,
            }
        }


class SkillsMatch(BaseModel):
    """Detailed skills matching information"""

    required_skills_matched: List[str] = Field(
        default=[], description="Matched required skills"
    )
    preferred_skills_matched: List[str] = Field(
        default=[], description="Matched preferred skills"
    )
    missing_required_skills: List[str] = Field(
        default=[], description="Missing required skills"
    )
    missing_preferred_skills: List[str] = Field(
        default=[], description="Missing preferred skills"
    )
    skill_match_percentage: float = Field(
        ..., ge=0, le=100, description="Percentage of skills matched"
    )

    class Config:
        schema_extra = {
            "example": {
                "required_skills_matched": ["Python", "FastAPI"],
                "preferred_skills_matched": ["Docker"],
                "missing_required_skills": ["AWS"],
                "missing_preferred_skills": ["React", "Kubernetes"],
                "skill_match_percentage": 66.7,
            }
        }


class DocumentAnalysisResult(BaseModel):
    """Main response model for document analysis"""

    extracted_text: str = Field(..., description="Raw extracted text from document")
    structured_data: StructuredResumeData = Field(
        ..., description="Structured resume data"
    )
    overall_score: float = Field(
        ..., ge=0, le=100, description="Overall match score (0-100)"
    )
    score_breakdown: ScoreBreakdown = Field(
        ..., description="Detailed scoring breakdown"
    )
    skills_match: SkillsMatch = Field(..., description="Skills matching details")
    key_insights: List[str] = Field(..., description="Key insights and recommendations")
    processing_time: float = Field(..., ge=0, description="Processing time in seconds")
    confidence_scores: Dict[str, float] = Field(
        default={}, description="Confidence scores for extracted data"
    )
    
    question_for_interview: Optional[List[str]] = Field(
        default=None, description="Generated interview questions for the candidate"
    )
    
    go_job_posting_id: Optional[str] = Field(default=None, description="id for the job in golang")
    resume_url: Optional[str] = Field(default=None, description="C:\Games\Storage\v1\a4cade3e-be10-431b-b943-f9da88606d67\resume 2024.pdf")

    class Config:
        schema_extra = {
            "example": {
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
                "question_for_interview": [
                    "Can you describe your experience with Python in previous projects?",
                    "How have you utilized FastAPI in your past work?",
                    "What strategies do you use to stay updated with new technologies?",
                ],
                "go_job_posting_id": "4de68d8d-f192-4735-9e3c-294240cbbc9e",
                "resume_url": "C:\\Games\\Storage\\v1\\a4cade3e-be10-431b-b943-f9da88606d67\\resume 2024.pdf"
            }
        }


class DocumentBatchAnalysisResult(BaseModel):
    """Response model for batch document analysis"""

    job_posting_id: Optional[str] = Field(None, description="Job posting ID")
    analyses: List[DocumentAnalysisResult] = Field(
        ..., description="List of analysis results"
    )
    total_processed: int = Field(..., description="Total documents processed")
    processing_summary: Dict[str, Any] = Field(
        ..., description="Processing summary statistics"
    )

    class Config:
        schema_extra = {
            "example": {
                "job_posting_id": "job_123",
                "analyses": [],
                "total_processed": 5,
                "processing_summary": {
                    "average_score": 75.2,
                    "top_candidate_score": 92.5,
                    "skills_gap_analysis": {"Python": 80, "AWS": 40},
                },
            }
        }
