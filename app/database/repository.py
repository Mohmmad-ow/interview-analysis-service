from sqlalchemy.orm import Session
from app.database.models import AnalysisResultDB, AuditLog, ErrorLog
from app.models import analysis
from app.models.analysis.response import AnalysisResult
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from app.database.connection import db_manager
from app.models.audit.request import AuditLog as AuditLogModel
from app.models.job.status import (
    JobResultResponse,
    JobStatusResponse,
    JobsResultRequest,
    JobsResultResponse,
    JobsStatusResponse,
    RequestJobsStatus,
)


class AnalysisRepository:
    def __init__(self, session: Session):
        self.session = session

    async def save_analysis_result(
        self,
        job_id: str,
        user_id: str,
        audio_url: str,
        job_description: str,
        callback_url: Optional[str],
        questions: Optional[List[str]],
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
            job_description=job_description,
            callback_url=callback_url,
            questions=questions if questions is not None else [],
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

    async def get_job_status_by_id(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get job status by job ID"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .first()
        )
        if result:
            return JobStatusResponse(
                job_id=str(result.job_id),
                status=str(result.status),
                result_url=(
                    None
                    if str(result.status) != "completed"
                    else f"/v1/analysis/{result.job_id}/result"
                ),
            )
        return None

    async def get_job_status(
        self, job_request: RequestJobsStatus
    ) -> JobsStatusResponse:
        """Get job status based on filters"""
        query = self.session.query(AnalysisResultDB)

        if job_request.job_ids:
            query = query.filter(AnalysisResultDB.job_id.in_(job_request.job_ids))
        if job_request.status:
            query = query.filter(AnalysisResultDB.status == job_request.status.value)
        if job_request.start_date and job_request.end_date:
            query = query.filter(
                AnalysisResultDB.created_at >= job_request.start_date,
                AnalysisResultDB.created_at <= job_request.end_date,
            )
        if job_request.user_id:
            query = query.filter(AnalysisResultDB.user_id == job_request.user_id)
        total_count = query.count()
        results = query.offset(job_request.offset).limit(job_request.limit).all()
        pages = (total_count + job_request.limit - 1) // job_request.limit
        current_page = (job_request.offset // job_request.limit) + 1
        result = JobsStatusResponse(
            jobs=[
                JobStatusResponse(
                    job_id=str(result.job_id),
                    status=str(result.status),
                    result_url=(
                        None
                        if str(result.status) != "completed"
                        else f"/v1/analysis/{result.job_id}/result"
                    ),
                )
                for result in results
            ],
            total_count=total_count,
            offset=job_request.offset,
            limit=job_request.limit,
            pages=pages,
            current_page=current_page,
        )
        return result

    async def get_jobs_result(
        self, job_request: JobsResultRequest
    ) -> JobsResultResponse:
        """Get job results based on filters"""
        query = self.session.query(AnalysisResultDB)
        query = query.filter(AnalysisResultDB.status == "completed")
        if job_request.job_ids:
            query = query.filter(AnalysisResultDB.job_id.in_(job_request.job_ids))
        if job_request.start_date and job_request.end_date:
            query = query.filter(
                AnalysisResultDB.created_at >= job_request.start_date,
                AnalysisResultDB.created_at <= job_request.end_date,
            )
        if job_request.user_id:
            query = query.filter(AnalysisResultDB.user_id == job_request.user_id)
        total_count = query.count()
        pages = (total_count + job_request.limit - 1) // job_request.limit
        current_page = (job_request.offset // job_request.limit) + 1
        results = query.offset(job_request.offset).limit(job_request.limit).all()
        parsed_results: list[JobResultResponse] = []
        for result in results:
            parsed_results.append(
                JobResultResponse(
                    job_id=str(result.job_id),
                    analysis_result=self.parse_analysis_result(result),
                )
            )
        return JobsResultResponse(
            jobs=parsed_results,
            total_count=total_count,
            offset=job_request.offset,
            limit=job_request.limit,
            pages=pages,
            current_page=current_page,
        )

    def parse_analysis_result(self, result: AnalysisResultDB) -> AnalysisResult:
        """Parse AnalysisResultDB to AnalysisResult"""
        confidence_indicators = {}
        if result.confidence_data:  # type: ignore
            if isinstance(result.confidence_data, dict):
                confidence_indicators = result.confidence_data
            elif isinstance(result.confidence_data, str):
                import json

                confidence_indicators = json.loads(result.confidence_data)

        key_insights = []
        if result.key_insights:  # type: ignore
            if isinstance(result.key_insights, list):
                key_insights = result.key_insights
            elif isinstance(result.key_insights, str):
                import json

                key_insights = json.loads(result.key_insights)

        return AnalysisResult(
            transcript=str(result.transcript) or "",
            technical_score=result.technical_score or 0.0,  # type: ignore
            communication_score=result.communication_score or 0.0,  # type: ignore
            confidence_indicators=confidence_indicators or {},
            key_insights=key_insights or [],
            processing_time=result.processing_time or 0.0,  # type: ignore
        )

    async def get_job_result(self, job_id: str) -> Optional[AnalysisResultDB]:
        """Get job result by job ID"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(
                AnalysisResultDB.job_id == job_id,
                AnalysisResultDB.status == "completed",
            )
            .first()
        )
        if result:
            return result
        return None

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
