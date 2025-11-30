from ast import List
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    DateTime,
    Boolean,
    Float,
    Text,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

from app.models import job

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource = Column(String(500))
    success = Column(Boolean, default=True)
    processing_time = Column(Float)
    error_type = Column(String(100))
    extrainfo = Column(JSON)

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(String(50), index=True)
    job_id = Column(String(100), index=True)
    error_type = Column(String(100), nullable=False, index=True)
    error_message = Column(Text)
    stack_trace = Column(Text)
    request_data = Column(JSON)
    resolved = Column(Boolean, default=False, index=True)

    def __repr__(self):
        return f"<ErrorLog {self.error_type} for job {self.job_id}>"


class DocumentAnalysisDB(Base):
    """Main document analysis table - simplified"""

    __tablename__ = "document_analysis"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(20), nullable=False)

    # Basic extracted fields
    extracted_text = Column(Text)
    candidate_name = Column(String(200))
    candidate_email = Column(String(200))
    candidate_phone = Column(String(50))

    # Simple scores
    overall_score = Column(Float)
    skills_score = Column(Float)
    experience_score = Column(Float)
    education_score = Column(Float)

    # Processing metadata
    status = Column(String(20), default="pending")
    processing_time = Column(Float)
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class DocumentEducationDB(Base):
    """Education history - normalized"""

    __tablename__ = "document_education"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("document_analysis.id"), index=True)
    institution = Column(String(300))
    degree = Column(String(200))
    field_of_study = Column(String(200))
    start_year = Column(Integer)
    end_year = Column(Integer)
    gpa = Column(Float)


class DocumentWorkExperienceDB(Base):
    """Work experience - normalized"""

    __tablename__ = "document_work_experience"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("document_analysis.id"), index=True)
    company = Column(String(300))
    title = Column(String(200))
    start_date = Column(String(100))  # Store as string for flexibility
    end_date = Column(String(100))
    description = Column(Text)
    duration_months = Column(Integer)


class DocumentSkillsDB(Base):
    """Skills - normalized"""

    __tablename__ = "document_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("document_analysis.id"), index=True)
    skill_name = Column(String(100))
    skill_category = Column(String(50))  # technical, soft, tool, etc.
    confidence = Column(Float)  # Extraction confidence


class DocumentSkillsMatchDB(Base):
    """Skills matching results - normalized"""

    __tablename__ = "document_skills_match"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("document_analysis.id"), index=True)
    required_skill = Column(String(100))
    is_matched = Column(Boolean)
    match_type = Column(String(20))  # exact, partial, missing
    confidence = Column(Float)


class DocumentKeyInsightsDB(Base):
    """Key insights - normalized"""

    __tablename__ = "document_key_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("document_analysis.id"), index=True)
    insight_text = Column(Text)
    insight_type = Column(String(50))  # strength, weakness, recommendation
    relevance_score = Column(Float)
