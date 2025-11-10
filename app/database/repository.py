from sqlalchemy.orm import Session
from app.database.models import AnalysisResultDB, AuditLog, ErrorLog
from app.models import analysis
from app.models.analysis.response import AnalysisResult
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from app.database.connection import db_manager
from app.models.audit.request import AuditLog as AuditLogModel


class AnalysisRepository:
    def __init__(self, session: Session):
        self.session = session

    async def save_analysis_result(
        self,
        job_id: str,
        user_id: str,
        audio_url: str,
        analysis_result: AnalysisResult,
        status: str = "completed",
    ) -> AnalysisResultDB:
        """Save analysis result to database"""
        db_result = AnalysisResultDB(
            job_id=job_id,
            user_id=user_id,
            audio_url=audio_url,
            transcript=analysis_result.transcript,
            technical_score=analysis_result.technical_score,
            communication_score=analysis_result.communication_score,
            confidence_data=analysis_result.confidence_indicators,
            key_insights=analysis_result.key_insights,
            processing_time=analysis_result.processing_time,
            status=status,
        )

        self.session.add(db_result)
        self.session.commit()
        self.session.refresh(db_result)
        return db_result

    async def get_analysis_result(self, job_id: str) -> Optional[AnalysisResultDB]:
        """Get analysis result by job ID"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .first()
        )

    async def get_user_analyses(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[AnalysisResultDB]:
        """Get analysis history for a user"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.user_id == user_id)
            .order_by(AnalysisResultDB.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    async def update_analysis_status(self, job_id: str, status: str) -> bool:
        """Update analysis job status"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .update({"status": status})
        )

        self.session.commit()
        return result > 0

    async def get_analysis_by_ids(self, job_ids: List[int]) -> List[AnalysisResultDB]:
        """Get multiple analysis results by job IDs"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id.in_(job_ids))
            .all()
        )

    async def get_all_queued_jobs(self) -> List[AnalysisResultDB]:
        """Get all analysis jobs with status 'queued'"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.status == "queued")
            .all()
        )

    async def get_queued_jobs_by_user(self, user_id: str) -> List[AnalysisResultDB]:
        """Get all queued analysis jobs for a specific user"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(
                AnalysisResultDB.status == "queued", AnalysisResultDB.user_id == user_id
            )
            .all()
        )

    async def get_queued_jobs_by_date(
        self, start_date: datetime, end_date: datetime
    ) -> List[AnalysisResultDB]:
        """Get all queued analysis jobs within a date range"""
        return (
            self.session.query(AnalysisResultDB)
            .filter(
                AnalysisResultDB.status == "queued",
                AnalysisResultDB.created_at >= start_date,
                AnalysisResultDB.created_at <= end_date,
            )
            .all()
        )

    async def update_job_status(self, job_id: str, status: str) -> bool:
        """Update job status by job ID"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .update({"status": status})
        )

        self.session.commit()
        return result > 0


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    async def get_recent_audit_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        hours: int = 24,
    ) -> List[AuditLog]:
        """Get recent audit logs with filters"""
        query = self.session.query(AuditLog).filter(
            AuditLog.timestamp >= datetime.utcnow() - timedelta(hours=hours)
        )

        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)

        return query.order_by(AuditLog.timestamp.desc()).all()

    async def update_job_status(self, id: int, status: str) -> bool:
        """Update job status by job ID"""
        result = (
            self.session.query(AuditLog)
            .filter(AuditLog.id == id)
            .update({"action": status})
        )
        return result > 0

    async def log_audit_event(self, log: AuditLogModel) -> AuditLog:
        """Create an audit log event"""
        AuditLogEntry = AuditLog(
            user_id=log.user_id,
            action=log.action,
            resource=log.resource_pattern,
            success=log.success_only,
            processing_time=log.processing_time,
            error_type=log.error_type,
            extrainfo=log.metadata,
        )
        self.session.add(AuditLogEntry)
        self.session.commit()
        self.session.refresh(AuditLogEntry)
        return AuditLogEntry

    def log_error(
        self,
        user_id: str,
        job_id: str,
        error_type: str,
        error_message: str,
        stack_trace: str,
        request_data: Dict,
        resolved: bool = False,
    ) -> ErrorLog:
        """Log an error event"""
        error_log = ErrorLog(
            user_id=user_id,
            job_id=job_id,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            request_data=request_data,
            resolved=resolved,
        )
        self.session.add(error_log)
        self.session.commit()
        self.session.refresh(error_log)
        return error_log


# Initialize repositories with a session


session = db_manager.SessionLocal()

analysis_repository = AnalysisRepository(session)
audit_repository = AuditRepository(session)
