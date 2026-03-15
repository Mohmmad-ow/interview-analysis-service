from aiohttp import web
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.database.models import AnalysisResultDB, AuditLog, ErrorLog, WebhookDelivery
from app.models import analysis
from app.models.analysis.response import AnalysisResult
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta, timezone
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
    
    async def delete_analysis_result(self, job_id: str) -> bool:
        """Delete analysis result by job ID"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .delete()
        )
        self.session.commit()
        return result > 0

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

    async def change_analysis_status(self, job_id: str):
        pass

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

    async def update_analysis_status(
        self, job_id: str, status: str, analysis_result: AnalysisResult
    ) -> bool:
        """Update analysis job status"""
        result = (
            self.session.query(AnalysisResultDB)
            .filter(AnalysisResultDB.job_id == job_id)
            .update(
                {
                    "status": status,
                    "transcript": analysis_result.transcript,
                    "technical_score": analysis_result.technical_score,
                    "communication_score": analysis_result.communication_score,
                    "key_insights": analysis_result.key_insights,
                    "confidence_data": analysis_result.confidence_indicators,
                    "processing_time": analysis_result.processing_time,
                }
            )
        )

        self.session.commit()
        return result > 0

    async def get_analysis_by_ids(self, job_ids: List[str]) -> List[AnalysisResultDB]:
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

    async def log_error(
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


# app/database/repository.py - add to AuditRepository or create new


class WebhookRepository:
    def __init__(self, session: Session):
        self.session = session

    async def create_delivery_record(
        self,
        job_id: str,
        callback_url: str,
        user_id: Optional[str] = None,
        max_attempts: int = 3,
    ) -> WebhookDelivery:
        """Create a new webhook delivery record"""
        delivery = WebhookDelivery(
            job_id=job_id,
            callback_url=callback_url,
            status="pending",
            max_attempts=max_attempts,
            created_by=user_id,
        )
        self.session.add(delivery)
        self.session.commit()
        self.session.refresh(delivery)
        return delivery

    async def get_delivery(self, job_id: str) -> Optional[WebhookDelivery]:
        """Get webhook delivery record by job ID"""
        return (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.job_id == job_id)
            .first()
        )

    async def update_delivery_attempt(
        self,
        job_id: str,
        attempt_number: int,
        status: str,
        response_status: Optional[int] = None,
        response_headers: Optional[Dict] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> bool:
        """Update webhook delivery after an attempt"""
        delivery = self.session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.job_id == job_id)
            .values(
                attempts=attempt_number if attempt_number else WebhookDelivery.attempts,
                last_attempt=(
                    datetime.now(timezone.utc)
                    if attempt_number
                    else WebhookDelivery.last_attempt
                ),
                status=status if status else WebhookDelivery.status,
                response_status=(
                    response_status
                    if response_status
                    else WebhookDelivery.response_status
                ),
                response_headers=(
                    response_headers
                    if response_headers
                    else WebhookDelivery.response_headers
                ),
                response_body=response_body[:1000] if response_body else None,
                error_message=(
                    error_message if error_message else WebhookDelivery.error_message
                ),
                error_type=error_type if error_type else WebhookDelivery.error_type,
            )
        )

        self.session.commit()
        return True

    async def get_pending_retries(self) -> List[WebhookDelivery]:
        """Get webhooks that need retry"""
        now = datetime.utcnow()
        return (
            self.session.query(WebhookDelivery)
            .filter(
                WebhookDelivery.status.in_(["failed", "retrying"]),
                WebhookDelivery.attempts < WebhookDelivery.max_attempts,
                WebhookDelivery.next_retry_at <= now,
            )
            .all()
        )

    async def get_webhook_stats(
        self, user_id: Optional[str] = None, days: int = 7
    ) -> Dict[str, Any]:
        """Get webhook delivery statistics"""
        query = self.session.query(WebhookDelivery)

        if user_id:
            query = query.filter(WebhookDelivery.created_by == user_id)

        # Filter by date
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(WebhookDelivery.created_at >= since)

        total = query.count()
        delivered = query.filter(WebhookDelivery.status == "delivered").count()
        failed = query.filter(WebhookDelivery.status == "failed").count()
        pending = query.filter(WebhookDelivery.status == "pending").count()

        # Calculate success rate
        success_rate = (delivered / total * 100) if total > 0 else 0

        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "success_rate": round(success_rate, 2),
            "period_days": days,
        }

    def get_failed_webhooks(self, limit: int = 50) -> List[WebhookDelivery]:
        """Get recent failed webhooks"""
        return (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.status == "failed")
            .order_by(WebhookDelivery.last_attempt.desc())
            .limit(limit)
            .all()
        )


session = db_manager.SessionLocal()
webhook_repo = WebhookRepository(session)
analysis_repository = AnalysisRepository(session)
audit_repository = AuditRepository(session)
