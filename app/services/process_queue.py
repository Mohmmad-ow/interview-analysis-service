import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.logging import log_info, log_error, log_warning
from app.database.models import AnalysisResultDB
from app.models.analysis.request import AsyncProcessQueuedJobs, QueuedJobType
from app.models.analysis.response import AnalysisResult
from app.models.audit.request import AuditAction, AuditLog
from app.services.webhook_service import webhook_service
from app.services.whisper_service import whisper_service
from app.services.GeminiAnalysis import gemini_service
from app.database.repository import analysis_repository, audit_repository


class JobProcessor:
    def __init__(self, max_concurrent_jobs: int = 3):
        self.max_concurrent_jobs = max_concurrent_jobs
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        self._is_processing = False
        self._current_batch_id = None

    async def process_queued_jobs(
        self, queued_jobs_request: AsyncProcessQueuedJobs
    ) -> Dict[str, Any]:
        """Process queued analysis jobs with proper state management"""
        if self._is_processing:
            raise Exception("Job processor is already running")

        self._is_processing = True
        self._current_batch_id = (
            f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        )

        try:
            log_info(f"Starting job processing batch: {self._current_batch_id}")

            # 1. Fetch jobs based on criteria
            print(f"Jobs Processing Request {queued_jobs_request}")
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
            start_time = datetime.now(timezone.utc)

            # 2. Process jobs in controlled batches
            results = await self._process_job_batch(jobs)

            # 3. Return processing summary
            summary = {
                "batch_id": self._current_batch_id,
                "processed": len(jobs),
                "successful": results["successful"],
                "failed": results["failed"],
                "start_time": start_time.isoformat(),
                "end_time": datetime.now(timezone.utc).isoformat(),
            }

            log_info(f"Batch {self._current_batch_id} completed: {summary}")
            return summary

        except Exception as e:
            log_error(f"Job processing failed for batch {self._current_batch_id}: {e}")
            raise
        finally:
            self._is_processing = False
            self._current_batch_id = None

    async def _fetch_jobs(
        self, request: AsyncProcessQueuedJobs
    ) -> List[AnalysisResultDB]:
        """Fetch jobs based on request type using repository pattern"""

        if request.job_type == QueuedJobType.PROCESSVIAIDS and request.job_ids:
            return await analysis_repository.get_analysis_by_ids(request.job_ids)
        elif request.job_type == QueuedJobType.PROCESSALL:
            return await analysis_repository.get_all_queued_jobs()
        elif request.job_type == QueuedJobType.PROCESSVIAUSER:
            return await analysis_repository.get_queued_jobs_by_user(request.user_id)
        elif (
            request.job_type == QueuedJobType.PROCESSVIADATE
            and request.start_date
            and request.end_date
        ):
            return await analysis_repository.get_queued_jobs_by_date(
                request.start_date, request.end_date
            )
        return []

    async def _process_job_batch(self, jobs: List[AnalysisResultDB]) -> Dict[str, int]:
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
                task = asyncio.create_task(self._process_single_job_with_semaphore(job))
                batch_tasks.append(task)

            # Wait for batch completion
            batch_results = asyncio.gather(*batch_tasks, return_exceptions=True)

            # Count results
            for job, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    log_error(f"Job {job.job_id} failed: {result}")
                    failed += 1
                else:
                    log_info(f"Job {job.job_id} completed successfully")
                    successful += 1

            log_info(
                f"Batch {i//batch_size + 1} complete: {successful} successful, {failed} failed so far"
            )

            # Small delay between batches to prevent resource exhaustion
            if i + batch_size < len(jobs):
                await asyncio.sleep(2)  # 2-second cooldown between batches

        return {"successful": successful, "failed": failed}

    async def _process_single_job_with_semaphore(self, job: AnalysisResultDB):
        """Process a single job with concurrency control"""
        async with self.semaphore:
            return await self._process_single_job(job)

    async def _process_single_job(self, job: AnalysisResultDB):
        """Process a single analysis job from queued to completed"""

        try:
            # 1. Update status to processing
            await analysis_repository.update_job_status(str(job.job_id), "processing")
            log_info(f"Started processing job {job.job_id}")

            # 2. Perform the actual analysis
            analysis_result = await self._perform_complete_analysis(job)

            # 3. Save the completed results
            await analysis_repository.update_analysis_status(
                job_id=str(job.job_id),
                status="completed",
                analysis_result=analysis_result,
            )

            log_entry = AuditLog(
                user_id=str(job.user_id),
                action=AuditAction.ANALYSIS_COMPLETED,
                resource_pattern=str(job.audio_url),
                success_only=True,
                metadata={
                    "job_id": job.job_id,
                    "processing_time": analysis_result.processing_time,
                    "technical_score": analysis_result.technical_score,
                },
            )
            # 4. Log successful completion
            await audit_repository.log_audit_event(log=log_entry)

            log_info(f"Successfully completed job {job.job_id}")
            return analysis_result

        except Exception as e:
            # 5. Handle failures
            log_error(f"Failed to process job {job.job_id}: {str(e)}")
            await analysis_repository.update_job_status(str(job.job_id), "failed")

            # Log error
            await audit_repository.log_error(
                user_id=str(job.user_id),
                job_id=str(job.job_id),
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace="",  # You can add proper traceback here
                request_data={"audio_url": job.audio_url},
            )
            raise e

    async def _perform_complete_analysis(self, job: AnalysisResultDB) -> AnalysisResult:
        """Complete analysis pipeline for a single job"""
        start_time = asyncio.get_event_loop().time()

        try:
            # 1. Transcription
            log_info(f"Starting transcription for job {job.job_id}")

            if str(job.audio_url).startswith(("http://", "https://")):
                transcript, transcription_time = (
                    await whisper_service.transcribe_audio_url(
                        str(job.audio_url),
                    )
                )
            else:
                transcript, transcription_time = (
                    await whisper_service.transcribe_local_file(str(job.audio_url))
                )

            log_info(
                f"Transcription completed for job {job.job_id}: {len(transcript)} characters"
            )

            # 2. Get job description and questions from stored data
            job_description = getattr(job, "job_description", "")
            questions = getattr(job, "questions", [])

            if not job_description:
                raise ValueError("Job description missing from queued job")

            # 3. Gemini Analysis
            log_info(f"Starting Gemini analysis for job {job.job_id}")

            gemini_analysis = await gemini_service.analyze_interview(
                transcript=transcript,
                job_description=job_description,
                questions=questions if questions else None,
            )

            # 4. Calculate total processing time
            total_processing_time = asyncio.get_event_loop().time() - start_time

            # 5. Create final result
            analysis_result = AnalysisResult(
                transcript=transcript,
                technical_score=gemini_analysis["technical_score"],
                communication_score=gemini_analysis["communication_score"],
                confidence_indicators=gemini_analysis["confidence_indicators"],
                key_insights=gemini_analysis["key_insights"],
                processing_time=total_processing_time,
            )

            log_info(f"Analysis completed for job {job.job_id}")
            return analysis_result

        except Exception as e:
            log_error(f"Analysis pipeline failed for job {job.job_id}: {str(e)}")
            raise e
        finally:
            callback_url = getattr(job, "callback_url", None)
            if callback_url and analysis_result:
                # ✅ Convert Pydantic model to dict before adding new keys
                result_data = (
                    analysis_result.dict()
                    if hasattr(analysis_result, "dict")
                    else vars(analysis_result)
                )
                result_data["audio_url"] = job.audio_url

                status = "completed"

                asyncio.create_task(
                    webhook_service.send_webhook(
                        callback_url=callback_url,
                        job_id=str(job.job_id),
                        status=status,
                        result=result_data,  # Send the dict
                        error=None,
                        user_id=str(job.user_id),
                    )
                )

    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processor status"""
        return {
            "is_processing": self._is_processing,
            "current_batch_id": self._current_batch_id,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "timestamp": datetime.utcnow().isoformat(),
        }


# Global processor instance
job_processor = JobProcessor(max_concurrent_jobs=3)
