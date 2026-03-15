from ast import List
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, JSON
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


class AnalysisResultDB(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    audio_url = Column(String(500))
    job_description = Column(Text)
    callback_url = Column(String(500))
    questions = Column(JSON, nullable=True)
    transcript = Column(Text)
    technical_score = Column(Float)
    communication_score = Column(Float)
    confidence_data = Column(JSON)
    key_insights = Column(JSON)
    processing_time = Column(Float)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), index=True)
    status = Column(String(50), default="completed", index=True)

    def __repr__(self):
        return f"<AnalysisResult {self.job_id} for user {self.user_id}>"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(100), nullable=False, index=True)
    callback_url = Column(String(500), nullable=False)

    # Delivery status
    status = Column(
        String(20), default="pending"
    )  # pending, delivered, failed, retrying
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    last_attempt = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    # Response details
    response_status = Column(Integer, nullable=True)  # HTTP status code from client
    response_headers = Column(JSON, nullable=True)
    response_body = Column(Text, nullable=True)  # Truncated response

    # Error details
    error_type = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    # Payload sent
    payload_sent = Column(JSON, nullable=True)  # What we sent

    # Metadata
    next_retry_at = Column(DateTime, nullable=True)
    created_by = Column(String(50), nullable=True)  # user_id

    def __repr__(self):
        return f"<WebhookDelivery job={self.job_id} status={self.status}>"
