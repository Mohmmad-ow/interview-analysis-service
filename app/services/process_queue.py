import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from enum import Enum

from app.core.logging import log_info, log_error, log_warning
from app.database.models import DocumentAnalysisDB
from app.models.analysis.request import AsyncProcessQueuedJobs, QueuedJobType
from app.models.analysis.response import DocumentAnalysisResult
from app.models.audit.request import AuditAction, AuditLog
from app.services.GeminiAnalysis import gemini_service
from app.services.analysis import document_analysis_service
from app.database.repository import analysis_repository, audit_repository


class JobType(str, Enum):
    INTERVIEW = "interview"
    DOCUMENT = "document"


class JobProcessor:
    def __init__(self, max_concurrent_jobs: int = 3):
        self.max_concurrent_jobs = max_concurrent_jobs
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        self._is_processing = False
        self._current_batch_id = None
        self._current_job_type = None

    async def process_queued_jobs(
        self, queued_jobs_request: AsyncProcessQueuedJobs
    ) -> Dict[str, Any]:
        """Process queued analysis jobs with proper state management"""
        if self._is_processing:
            raise Exception("Job processor is already running")

        self._is_processing = True
        self._current_batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self._current_job_type = queued_jobs_request.job_type

        try:
            log_info(
                f"Starting job processing batch: {self._current_batch_id}, "
                f"type: {queued_jobs_request.job_type}"
            )

            # 1. Fetch jobs based on criteria
            jobs = await self._fetch_jobs(queued_jobs_request)
            if not jobs:
                log_info("No jobs to process")
                return {
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "batch_id": self._current_batch_id,
                }

            log_info(
                f"Found {len(jobs)} jobs to process in batch {self._current_batch_id}"
            )

            # 2. Process jobs in controlled batches
            results = await self._process_job_batch(jobs)

            # 3. Return processing summary
            summary = {
                "batch_id": self._current_batch_id,
                "processed": len(jobs),
                "successful": results["successful"],
                "failed": results["failed"],
                "start_time": datetime.utcnow().isoformat(),
                "end_time": datetime.utcnow().isoformat(),
            }

            log_info(f"Batch {self._current_batch_id} completed: {summary}")
            return summary

        except Exception as e:
            log_error(f"Job processing failed for batch {self._current_batch_id}: {e}")
            raise
        finally:
            self._is_processing = False
            self._current_batch_id = None
            self._current_job_type = None

    async def _fetch_jobs(
        self, request: AsyncProcessQueuedJobs
    ) -> List[DocumentAnalysisDB]:
        """Fetch jobs based on request type and job type"""
        return await self._fetch_document_jobs(request)

    async def _fetch_document_jobs(
        self, request: AsyncProcessQueuedJobs
    ) -> List[DocumentAnalysisDB]:
        """Fetch document analysis jobs"""
        if request.job_type == QueuedJobType.PROCESSVIAIDS and request.job_ids:
            return await analysis_repository.get_document_analysis_by_ids(
                request.job_ids
            )
        elif request.job_type == QueuedJobType.PROCESSALL:
            return await analysis_repository.get_all_queued_document_jobs()
        elif request.job_type == QueuedJobType.PROCESSVIAUSER:
            return await analysis_repository.get_queued_document_jobs_by_user(
                request.user_id
            )
        elif (
            request.job_type == QueuedJobType.PROCESSVIADATE
            and request.start_date
            and request.end_date
        ):
            # You'll need to implement get_queued_document_jobs_by_date in repository
            return await analysis_repository.get_queued_document_jobs_by_date(
                request.start_date, request.end_date
            )
        return []

    async def _process_job_batch(
        self, jobs: List[DocumentAnalysisDB]
    ) -> Dict[str, int]:
        """Process a batch of jobs with concurrency control"""
        successful = 0
        failed = 0

        # Process in batches to control resource usage
        batch_size = self.max_concurrent_jobs

        for i in range(0, len(jobs), batch_size):
            batch = jobs[i : i + batch_size]
            log_info(f"Processing batch {i//batch_size + 1} with {len(batch)} jobs")

            # Create tasks for current batch
            batch_tasks = []
            for job in batch:
                task = asyncio.create_task(
                    self._process_single_document_job_with_semaphore(job)
                )

                batch_tasks.append(task)

            # Wait for batch completion
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Count results
            for job, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    log_error(
                        f"Job {getattr(job, 'job_id', 'unknown')} failed: {result}"
                    )
                    failed += 1
                else:
                    log_info(
                        f"Job {getattr(job, 'job_id', 'unknown')} completed successfully"
                    )
                    successful += 1

            log_info(
                f"Batch {i//batch_size + 1} complete: {successful} successful, {failed} failed so far"
            )

            # Small delay between batches to prevent resource exhaustion
            if i + batch_size < len(jobs):
                await asyncio.sleep(2)  # 2-second cooldown between batches

        return {"successful": successful, "failed": failed}

    # ==================== DOCUMENT JOB PROCESSING ====================

    async def _process_single_document_job_with_semaphore(
        self, job: DocumentAnalysisDB
    ):
        """Process a single document job with concurrency control"""
        async with self.semaphore:
            return await self._process_single_document_job(job)

    async def _process_single_document_job(self, job: DocumentAnalysisDB):
        """Process a single document analysis job from queued to completed"""
        try:
            # 1. Update status to processing
            await analysis_repository.update_document_job_status(
                id=str(job.job_id), status="processing"
            )
            log_info(f"Started processing document job {job.job_id}")

            # 2. Perform the actual analysis using document analysis service
            analysis_result = await document_analysis_service.analyze_document_file(
                file_path=str(job.file_url),
                job_description=job.job_description,
                required_skills=job.required_skills or [],
                preferred_skills=job.preferred_skills or [],
                file_type=str(job.file_type),
            )

            # 3. Save the completed results
            await analysis_repository.update_document_analysis_status(
                job_id=str(job.job_id),
                status="completed",
                analysis_result=analysis_result,
            )

            # 4. Log successful completion
            await audit_repository.log_audit_event(
                AuditLog(
                    user_id=str(job.user_id),
                    action=AuditAction.ANALYSIS_COMPLETED,
                    resource_pattern=str(job.file_url),
                    success_only=True,
                    metadata={
                        "job_id": job.job_id,
                        "processing_time": analysis_result.processing_time,
                        "overall_score": analysis_result.overall_score,
                        "job_type": "document",
                    },
                )
            )

            log_info(f"Successfully completed document job {job.job_id}")
            return analysis_result

        except Exception as e:
            # 5. Handle failures
            log_error(f"Failed to process document job {job.job_id}: {str(e)}")
            await analysis_repository.update_document_job_status(
                id=str(job.job_id), status="failed"
            )

            # Log error
            await audit_repository.log_error(
                user_id=str(job.user_id),
                job_id=str(job.job_id),
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace="",
                request_data={
                    "file_url": str(job.file_url),
                    "file_type": job.file_type,
                    "job_type": "document",
                },
            )
            raise e

    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processor status"""
        return {
            "is_processing": self._is_processing,
            "current_batch_id": self._current_batch_id,
            "current_job_type": self._current_job_type,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "timestamp": datetime.utcnow().isoformat(),
        }


# Global processor instance
job_processor = JobProcessor(max_concurrent_jobs=3)
