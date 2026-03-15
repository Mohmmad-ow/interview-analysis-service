from datetime import timezone, datetime, timedelta
import json
import re
from httpcore import stream
from sqlalchemy import or_, update
from sqlalchemy.orm import Session, joinedload, contains_eager
from app.core.logging import log_error, log_info
from app.database.models import (
    AuditLog,
    DocumentEducationDB,
    DocumentKeyInsightsDB,
    DocumentSkillsDB,
    DocumentSkillsMatchDB,
    DocumentWorkExperienceDB,
    ErrorLog,
    DocumentAnalysisDB,
    WebhookDelivery
)  # ADD DocumentAnalysisDB
from app.models import analysis
from app.models.analysis.response import (
    DocumentAnalysisResult,
    ScoreBreakdown,
    SkillsMatch,
    StructuredResumeData,
)  # ADD DocumentAnalysisResult
from typing import Any, Optional, List, Dict, Tuple
from app.database.connection import db_manager
from app.models.audit.request import AuditLog as AuditLogModel
from app.models.job.status import (
    DocumentJobsResultRequest,
    DocumentJobsResultResponse,
    JobResultResponse,
    JobStatusResponse,
    JobsResultRequest,
    JobsResultResponse,
    JobsStatusResponse,
    RequestJobsStatus,
)

# app/database/repository.py - Improved document methods


class AnalysisRepository:
    def __init__(self, session: Session):
        self.session = session

    # ==================== DOCUMENT ANALYSIS METHODS ====================

    async def save_document_analysis_result(
        self,
        job_id: str,
        user_id: str,
        file_url: str,
        file_type: str,
        job_description: str,
        callback_url: Optional[str],
        required_skills: Optional[List[str]],
        preferred_skills: Optional[List[str]],
        go_job_posting_id: str,
        analysis_result: DocumentAnalysisResult,
        questions_for_interview: Optional[List[str]] = None,
        status: str = "completed",
        
    ) -> DocumentAnalysisDB:
        """Save document analysis result with normalized data and interview questions"""
        try:
            # Create main document analysis record
            db_document = DocumentAnalysisDB(
                job_id=job_id,
                user_id=user_id,
                file_url=file_url,
                file_type=file_type,
                callback_url=callback_url,
                extracted_text=analysis_result.extracted_text,
                candidate_questions=(
                    json.dumps(questions_for_interview) if questions_for_interview else None
                ),
                go_job_posting_id=go_job_posting_id,
                candidate_name=(
                    analysis_result.structured_data.name
                    if analysis_result.structured_data
                    else None
                ),
                candidate_email=(
                    analysis_result.structured_data.email
                    if analysis_result.structured_data
                    else None
                ),
                candidate_phone=(
                    analysis_result.structured_data.phone
                    if analysis_result.structured_data
                    else None
                ),
                overall_score=analysis_result.overall_score,
                skills_score=(
                    analysis_result.score_breakdown.skills_score
                    if analysis_result.score_breakdown
                    else 0.0
                ),
                experience_score=(
                    analysis_result.score_breakdown.experience_score
                    if analysis_result.score_breakdown
                    else 0.0
                ),
                education_score=(
                    analysis_result.score_breakdown.education_score
                    if analysis_result.score_breakdown
                    else 0.0
                ),
                status=status,
                processing_time=analysis_result.processing_time,
                completed_at=(
                    datetime.now(timezone.utc) if status == "completed" else None
                ),
            )

            self.session.add(db_document)
            self.session.flush()  # Get the ID for foreign keys

            # Save education history
            if (
                analysis_result.structured_data
                and analysis_result.structured_data.education
            ):
                for edu in analysis_result.structured_data.education:
                    db_edu = DocumentEducationDB(
                        document_id=db_document.id,
                        institution=edu.get("institution"),
                        degree=edu.get("degree"),
                        field_of_study=edu.get("field_of_study"),
                        start_year=edu.get("start_year"),
                        end_year=edu.get("end_year"),
                        gpa=edu.get("gpa"),
                    )
                    self.session.add(db_edu)

            # Save work experience
            if (
                analysis_result.structured_data
                and analysis_result.structured_data.work_experience
            ):
                for work in analysis_result.structured_data.work_experience:
                    db_work = DocumentWorkExperienceDB(
                        document_id=db_document.id,
                        company=work.get("company"),
                        title=work.get("title"),
                        start_date=work.get("start_date"),
                        end_date=work.get("end_date"),
                        description=work.get("description"),
                        duration_months=work.get("duration_months"),
                    )
                    self.session.add(db_work)

            # Save skills
            if (
                analysis_result.structured_data
                and analysis_result.structured_data.skills
            ):
                for skill in analysis_result.structured_data.skills:
                    db_skill = DocumentSkillsDB(
                        document_id=db_document.id,
                        skill_name=skill,
                        skill_category=self._categorize_skill(skill),
                        confidence=0.9,  # Default confidence
                    )
                    self.session.add(db_skill)

            # Save skills matching results
            if analysis_result.skills_match:
                # Save required skills matches
                for skill in required_skills or []:
                    is_matched = skill in (
                        analysis_result.skills_match.required_skills_matched or []
                    )
                    db_match = DocumentSkillsMatchDB(
                        document_id=db_document.id,
                        required_skill=skill,
                        is_matched=is_matched,
                        match_type="exact" if is_matched else "missing",
                        confidence=1.0 if is_matched else 0.0,
                    )
                    self.session.add(db_match)

            # Save key insights
            if analysis_result.key_insights:
                for insight in analysis_result.key_insights:
                    db_insight = DocumentKeyInsightsDB(
                        document_id=db_document.id,
                        insight_text=insight,
                        insight_type=self._classify_insight(insight),
                        relevance_score=0.8,  # Default relevance
                    )
                    self.session.add(db_insight)

            self.session.commit()
            return db_document

        except Exception as e:
            self.session.rollback()
            raise e

    async def parse_document_analysis_result(
        self, result: DocumentAnalysisDB
    ) -> DocumentAnalysisResult:
        """Robust parsing with proper error handling and interview questions"""
        try:
            # Eager load all related data
            
            education_records = await self._get_education_for_document(str(result.id))
            work_records = await self._get_work_experience_for_document(str(result.id))
            skill_records = await self._get_skills_for_document(str(result.id))
            skills_match_records = await self._get_skills_match_for_document(
                str(result.id)
            )
            insights_records = await self._get_insights_for_document(str(result.id))
            
            # Parse interview questions
            questions_for_interview = None
            if result.candidate_questions != None: # type: ignore
                try:
                    questions_for_interview = json.loads(result.candidate_questions) # type: ignore
                except (json.JSONDecodeError, TypeError):
                    questions_for_interview = None

            # Build structured data
            structured_data = StructuredResumeData(
                name=str(result.candidate_name) if str(result.candidate_name) else None,
                email=str(result.candidate_email) if str(result.candidate_email) else None,
                phone=str(result.candidate_phone) if str(result.candidate_phone) else None,
                education=education_records,
                work_experience=work_records,
                skills=[str(skill.skill_name) for skill in skill_records],
                certifications=[],  # You can add certifications table if needed
                languages=[],  # You can add languages table if needed
                summary=None,  # You can add summary field if needed
            )

            # Build score breakdown
            score_breakdown = ScoreBreakdown(
                skills_score=float(result.skills_score) or 0.0,  # type: ignore
                experience_score=float(result.experience_score) or 0.0,  # type: ignore
                education_score=float(result.education_score) or 0.0,  # type: ignore
                overall_fit=float(result.overall_score) or 0.0,  # type: ignore
            )

            # Build skills match
            required_matched = [
                str(sm.required_skill)
                for sm in skills_match_records
                if bool(sm.is_matched)
            ]
            missing_required = [
                str(sm.required_skill)
                for sm in skills_match_records
                if not bool(sm.is_matched)
            ]

            skills_match = SkillsMatch(
                required_skills_matched=required_matched,
                preferred_skills_matched=[],  # You can add preferred skills logic
                missing_required_skills=missing_required,
                missing_preferred_skills=[],
                skill_match_percentage=(
                    len(required_matched) / len(skills_match_records) * 100
                    if skills_match_records
                    else 0.0
                ),
            )

            # Build key insights
            key_insights = [str(insight.insight_text) for insight in insights_records]
            resume_url = self.strip_to_volume(str(result.file_url))
            log_info("Resume URL: " + resume_url)
            return DocumentAnalysisResult(
                go_job_posting_id=str(result.go_job_posting_id),
                resume_url=resume_url,
                extracted_text=str(result.extracted_text) or "",
                structured_data=structured_data,
                overall_score=float(result.overall_score) or 0.0,  # type: ignore
                score_breakdown=score_breakdown,
                skills_match=skills_match,
                key_insights=key_insights,
                processing_time=float(result.processing_time) or 0.0,  # type: ignore
                confidence_scores={},  # You can add confidence tracking if needed
                question_for_interview=questions_for_interview,
            )

        except Exception as e:
            log_error(f"Failed to parse document analysis result {result.id}: {str(e)}")
            # Return a safe default instead of crashing
            return self._create_safe_default_result(result)

    # Helper methods for related data
    async def _get_education_for_document(self, document_id: str) -> List[Dict]:
        records = (
            self.session.query(DocumentEducationDB)
            .filter(DocumentEducationDB.document_id == document_id)
            .all()
        )
        return [
            {
                "institution": record.institution,
                "degree": record.degree,
                "field_of_study": record.field_of_study,
                "start_year": record.start_year,
                "end_year": record.end_year,
                "gpa": record.gpa,
            }
            for record in records
        ]
    def strip_to_volume(self,path: str):
        """
        Removes all leading path components up to and including the volume marker.
        
        The volume marker is expected to be a folder name like 'v1', 'v2', ... 'v100'.
        
        Args:
            path (str): Original file path (e.g., r"C:\Games\Storage\v1\...\file.pdf")
        
        Returns:
            str: Path starting from the volume marker (e.g., "v1\...\file.pdf")
        """
        parts = path.split('\\')
        for i, part in enumerate(parts):
            if re.fullmatch(r'v\d+', part):          # matches exactly 'v' followed by digits
                return '\\'.join(parts[i:])
        return path   # fallback (or you could raise an exception)

    async def _get_work_experience_for_document(self, document_id: str) -> List[Dict]:
        records = (
            self.session.query(DocumentWorkExperienceDB)
            .filter(DocumentWorkExperienceDB.document_id == document_id)
            .all()
        )
        return [
            {
                "company": record.company,
                "title": record.title,
                "start_date": record.start_date,
                "end_date": record.end_date,
                "description": record.description,
                "duration_months": record.duration_months,
            }
            for record in records
        ]

    async def _get_skills_for_document(
        self, document_id: str
    ) -> List[DocumentSkillsDB]:
        return (
            self.session.query(DocumentSkillsDB)
            .filter(DocumentSkillsDB.document_id == document_id)
            .all()
        )

    async def _get_skills_match_for_document(
        self, document_id: str
    ) -> List[DocumentSkillsMatchDB]:
        return (
            self.session.query(DocumentSkillsMatchDB)
            .filter(DocumentSkillsMatchDB.document_id == document_id)
            .all()
        )

    async def _get_insights_for_document(
        self, document_id: str
    ) -> List[DocumentKeyInsightsDB]:
        return (
            self.session.query(DocumentKeyInsightsDB)
            .filter(DocumentKeyInsightsDB.document_id == document_id)
            .all()
        )

    def _create_safe_default_result(
        self, result: DocumentAnalysisDB
    ) -> DocumentAnalysisResult:
        """Create a safe default result when parsing fails"""
        questions_for_interview = None
        if result.candidate_questions != None: # type: ignore
            try:
                questions_for_interview: List[str] | None = json.loads(result.candidate_questions) # type: ignore
            except (json.JSONDecodeError, TypeError):
                questions_for_interview = None
        
        return DocumentAnalysisResult(
            extracted_text=str(result.extracted_text) or "",
            structured_data=StructuredResumeData(
                name="",
                email="",
                phone="",
                education=[],
                work_experience=[],
                skills=[],
                summary=None,
            ),
            overall_score=float(result.overall_score) or 0.0,  # type: ignore
            score_breakdown=ScoreBreakdown(
                skills_score=0.0,
                experience_score=0.0,
                education_score=0.0,
                overall_fit=0.0,
            ),
            skills_match=SkillsMatch(
                required_skills_matched=[],
                preferred_skills_matched=[],
                missing_required_skills=[],
                missing_preferred_skills=[],
                skill_match_percentage=0.0,
            ),
            key_insights=[],
            processing_time=result.processing_time or 0.0,  # type: ignore
            confidence_scores={},
            question_for_interview=questions_for_interview,
        )

    def _categorize_skill(self, skill: str) -> str:
        """Categorize skills - you can enhance this logic"""
        technical_keywords = ["python", "java", "sql", "docker", "aws", "fastapi"]
        if any(keyword in skill.lower() for keyword in technical_keywords):
            return "technical"
        return "other"

    def _classify_insight(self, insight: str) -> str:
        """Classify insights - you can enhance this logic"""
        if any(
            word in insight.lower()
            for word in ["strong", "excellent", "good", "impressive"]
        ):
            return "strength"
        elif any(
            word in insight.lower() for word in ["missing", "lack", "weak", "improve"]
        ):
            return "weakness"
        return "recommendation"

    async def get_all_queued_document_jobs(self) -> List[DocumentAnalysisDB]:
        """Retrieve all documents with status 'queued'"""
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.status == "queued")
            .all()
        )

    async def update_document_job_status(self, id: str, status: str) -> bool:
        """Update document analysis status by document ID"""
        result = (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.job_id == id)
            .update({"status": status})
        )
        return result > 0

    async def update_document_analysis_status(
        self, job_id: str, status: str, analysis_result: DocumentAnalysisResult
    ) -> bool:
        """Update document analysis status and result by job ID"""
        update_data = {
            "status": status,
            "candidate_name": analysis_result.structured_data.name,
            "candidate_email": analysis_result.structured_data.email,
            "candidate_phone": analysis_result.structured_data.phone,
            "extracted_text": analysis_result.extracted_text,
            "overall_score": analysis_result.overall_score,
            "processing_time": analysis_result.processing_time,
            "completed_at": datetime.now(timezone.utc),
        }
        
        # Include interview questions if present
        if analysis_result.question_for_interview:
            update_data["candidate_questions"] = json.dumps(
                analysis_result.question_for_interview
            )
        
        result = (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.job_id == job_id)
            .update(update_data) # type: ignore
        )
        return result > 0

    async def get_queued_jobs_filtered(self, limit: int = 10):
        """Retrieve queued document jobs with optional limit"""
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.status == "queued")
            .limit(limit)
            .all()
        )

    async def get_document_analysis_by_ids(self, job_ids: List[str]):
        """Get document analyses by a list of job IDs"""
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.job_id.in_(job_ids))
            .all()
        )

    async def get_queued_document_jobs_by_user(self, user_id: str):
        """
        Get all queued document analysis jobs for a specific user
        """
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(
                DocumentAnalysisDB.user_id == user_id,
                DocumentAnalysisDB.status == "queued",
            )
            .all()
        )

    async def get_queued_document_jobs_by_date(
        self, start_date: datetime, end_date: datetime
    ):
        """Get all queued document analysis jobs within a date range"""
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(
                DocumentAnalysisDB.status == "queued",
                DocumentAnalysisDB.created_at >= start_date,
                DocumentAnalysisDB.created_at <= end_date,
            )
            .all()
        )

    async def get_user_document_analyses(self, user_id: str):
        """
        Get all document analyses for a specific user
        """
        return (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.user_id == user_id)
            .all()
        )

    async def get_document_job_status(self, job_id: str) -> Optional[Dict]:
        """Get document job status by job ID"""
        document = (
            self.session.query(DocumentAnalysisDB)
            .filter(DocumentAnalysisDB.id == job_id)
            .first()
        )
        if document:
            return {
                "job_id": document.job_id,
                "status": document.status,
                "error_message": document.error_message,
            }
        return None

    async def get_document_job_result(
        self, job_id: str
    ) -> Optional[DocumentAnalysisResult]:
        """Retrieve document analysis job result with all related entities and interview questions"""
        try:
            # Use joinedload to fetch all related data in one query
            result = (
                self.session.query(DocumentAnalysisDB)
                .options(
                    joinedload(DocumentAnalysisDB.education_records),
                    joinedload(DocumentAnalysisDB.work_experience_records),
                    joinedload(DocumentAnalysisDB.skills_records),
                    joinedload(DocumentAnalysisDB.skills_match_records),
                    joinedload(DocumentAnalysisDB.key_insights_records),
                )
                .filter(
                    DocumentAnalysisDB.id == job_id,
                    DocumentAnalysisDB.status == "completed",
                )
                .first()
            )

            if not result:
                return None

            # Convert to DocumentAnalysisResult Pydantic model
            return await self.parse_document_analysis_result(result)

        except Exception as e:
            log_error(f"Failed to get document job result for {job_id}: {e}")
            return None

    async def get_document_jobs_result(
        self, request: DocumentJobsResultRequest
    ) -> DocumentJobsResultResponse:
        """Get document job results with filtering, pagination, and related data including interview questions"""
        try:
            # Base query with joins
            query = (
                self.session.query(DocumentAnalysisDB)
                .outerjoin(
                    DocumentEducationDB,
                    DocumentAnalysisDB.id == DocumentEducationDB.document_id,
                )
                # Join work experience records
                .outerjoin(
                    DocumentWorkExperienceDB,
                    DocumentAnalysisDB.id == DocumentWorkExperienceDB.document_id,
                )
                # Join skills records
                .outerjoin(
                    DocumentSkillsDB,
                    DocumentAnalysisDB.id == DocumentSkillsDB.document_id,
                )
                # Join skills match records
                .outerjoin(
                    DocumentSkillsMatchDB,
                    DocumentAnalysisDB.id == DocumentSkillsMatchDB.document_id,
                )
                # Join key insights records
                .outerjoin(
                    DocumentKeyInsightsDB,
                    DocumentAnalysisDB.id == DocumentKeyInsightsDB.document_id,
                )
                .filter(DocumentAnalysisDB.status == "completed")
            )

            # Apply filters
            query = self._apply_document_filters(query, request)

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination
            query = query.order_by(DocumentAnalysisDB.created_at.desc())
            query = query.offset(request.offset).limit(request.limit)

            # Execute query
            results = query.all()

            # Calculate pagination info
            pages = (total_count + request.limit - 1) // request.limit
            current_page = (request.offset // request.limit) + 1

            # Parse results to Pydantic models
            parsed_results = []
            for result in results:
                try:
                    parsed_result = await self.parse_document_analysis_result(result)
                    parsed_results.append(parsed_result)
                except Exception as e:
                    log_error(f"Failed to parse document result {result.job_id}: {e}")
                    continue

            # Build response
            return DocumentJobsResultResponse(
                jobs=parsed_results,
                total_count=total_count,
                offset=request.offset,
                limit=request.limit,
                pages=pages,
                current_page=current_page,
            )

        except Exception as e:
            log_error(f"Failed to get document jobs result: {e}")
            raise

    def _apply_document_filters(self, query, request: DocumentJobsResultRequest):
        """Apply filters to document query"""
        if request.job_ids:
            query = query.filter(DocumentAnalysisDB.job_id.in_(request.job_ids))

        if request.user_id:
            query = query.filter(DocumentAnalysisDB.user_id == request.user_id)

        if request.start_date and request.end_date:
            query = query.filter(
                DocumentAnalysisDB.created_at >= request.start_date,
                DocumentAnalysisDB.created_at <= request.end_date,
            )

        if hasattr(request, "min_score") and request.min_score is not None:
            query = query.filter(DocumentAnalysisDB.overall_score >= request.min_score)

        if hasattr(request, "max_score") and request.max_score is not None:
            query = query.filter(DocumentAnalysisDB.overall_score <= request.max_score)

        if hasattr(request, "file_type") and request.file_type:
            query = query.filter(DocumentAnalysisDB.file_type == request.file_type)

        return query

    async def search_document_analyses(
        self,
        search_term: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        file_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DocumentAnalysisResult], int]:
        """Search document analyses with advanced filtering and interview questions"""
        try:
            query = (
                self.session.query(DocumentAnalysisDB)
                .options(joinedload(DocumentAnalysisDB.skills_records))
                .filter(DocumentAnalysisDB.status == "completed")
            )

            # Apply filters
            if search_term:
                search_filter = or_(
                    DocumentAnalysisDB.candidate_name.ilike(f"%{search_term}%"),
                    DocumentAnalysisDB.candidate_email.ilike(f"%{search_term}%"),
                    DocumentAnalysisDB.extracted_text.ilike(f"%{search_term}%"),
                )
                query = query.filter(search_filter)

            if min_score is not None:
                query = query.filter(DocumentAnalysisDB.overall_score >= min_score)

            if max_score is not None:
                query = query.filter(DocumentAnalysisDB.overall_score <= max_score)

            if file_type:
                query = query.filter(DocumentAnalysisDB.file_type == file_type)

            if user_id:
                query = query.filter(DocumentAnalysisDB.user_id == user_id)

            # Get total count
            total_count = query.count()

            # Apply pagination
            query = query.order_by(DocumentAnalysisDB.overall_score.desc())
            query = query.offset(offset).limit(limit)

            # Execute and parse results
            results = query.all()
            parsed_results = [
                await self.parse_document_analysis_result(result) for result in results
            ]

            return parsed_results, total_count

        except Exception as e:
            log_error(f"Failed to search document analyses: {e}")
            raise


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

    async def update_job_status(
        self, id: int, status: str, error_message: str = ""
    ) -> bool:
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
                attempts=attempt_number,
                last_attempt=datetime.now(timezone.utc),
                status=status,
                response_status=response_status,
                response_headers=response_headers,
                response_body=response_body[:1000] if response_body else None,
                error_message=error_message,
                error_type=error_type,
                delivered_at=datetime.now(timezone.utc) if status == "delivered" else None,
                next_retry_at=self._calculate_next_retry(attempt_number) if status == "retrying" else None,
            )
        )

        self.session.commit()
        return True

    def _calculate_next_retry(self, attempt: int) -> datetime:
        """Calculate next retry time with exponential backoff"""
        delays = [60, 300, 900]  # 1 min, 5 min, 15 min
        delay = delays[min(attempt - 1, len(delays) - 1)]
        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    async def get_pending_retries(self) -> List[WebhookDelivery]:
        """Get webhooks that need retry"""
        now = datetime.now(timezone.utc)
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
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(WebhookDelivery.created_at >= since)

        total = query.count()
        delivered = query.filter(WebhookDelivery.status == "delivered").count()
        failed = query.filter(WebhookDelivery.status == "failed").count()
        pending = query.filter(WebhookDelivery.status == "pending").count()
        retrying = query.filter(WebhookDelivery.status == "retrying").count()

        # Calculate success rate
        success_rate = (delivered / total * 100) if total > 0 else 0

        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "retrying": retrying,
            "success_rate": round(success_rate, 2),
            "period_days": days,
        }

    async def get_failed_webhooks(self, limit: int = 50) -> List[WebhookDelivery]:
        """Get recent failed webhooks"""
        return (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.status == "failed")
            .order_by(WebhookDelivery.last_attempt.desc())
            .limit(limit)
            .all()
        )


session = db_manager.SessionLocal()
webhook_repository = WebhookRepository(session)
analysis_repository = AnalysisRepository(session)
audit_repository = AuditRepository(session)