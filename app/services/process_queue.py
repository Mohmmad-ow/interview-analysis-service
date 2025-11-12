import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
import logging
from app.database.repository import analysis_repository, audit_repository
from app.core.logging import log_error, log_info
from app.database.models import AnalysisResultDB
from app.models.analysis.request import AsyncProcessQueuedJobs, QueuedJobType
from app.services.whisper_service import whisper_service
from app.services.GeminiAnalysis import gemini_service
from app.models.analysis.response import AnalysisResult
import json


class AsyncJobProcessor:
    def __init__(self, max_concurrent_jobs: int = 3):
        self.max_concurrent_jobs = max_concurrent_jobs
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        # Thread pool for CPU-intensive work
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_jobs)

    async def process_queued_jobs(self, queued_jobs_request: AsyncProcessQueuedJobs):
        """Process jobs concurrently with rate limiting"""
        log_info("Starting async job processing")

        # 1. Fetch jobs based on criteria
        jobs = await self._fetch_jobs(queued_jobs_request)
        if not jobs:
            log_info("No jobs to process")
            return {"processed": 0, "successful": 0, "failed": 0}

        log_info(f"Found {len(jobs)} jobs to process")

        # 2. Process jobs in batches to avoid overwhelming the system
        batch_size = self.max_concurrent_jobs
        successful = 0
        failed = 0

        for i in range(0, len(jobs), batch_size):
            batch = jobs[i : i + batch_size]
            log_info(f"Processing batch {i//batch_size + 1} with {len(batch)} jobs")

            # Process current batch concurrently
            batch_tasks = [
                asyncio.create_task(self._process_single_job_with_semaphore(job))
                for job in batch
            ]

            # Wait for batch completion
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Process batch results
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
                await asyncio.sleep(1)

        log_info(f"Job processing complete: {successful} successful, {failed} failed")
        return {"processed": len(jobs), "successful": successful, "failed": failed}

    async def _fetch_jobs(
        self, request: AsyncProcessQueuedJobs
    ) -> List[AnalysisResultDB]:
        """Fetch jobs based on request type"""
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

    async def _process_single_job_with_semaphore(self, job: AnalysisResultDB):
        """Process a single job with concurrency control"""
        async with self.semaphore:
            return await self._process_single_job(job)

    async def _process_single_job(self, job: AnalysisResultDB):
        """Actual job processing logic"""
        try:
            # Update status to processing
            await analysis_repository.update_job_status(str(job.job_id), "processing")
            log_info(f"Started processing job {job.job_id}")

            # Step 1: Get job data (you need to store the original request)
            request_data = await self._get_job_request_data(job)

            # Step 2: Perform the actual analysis
            # This mixes I/O (Whisper API) and CPU work (Gemini processing)
            analysis_result = await self._perform_complete_analysis(request_data)

            # Step 3: Save the results
            await analysis_repository.save_analysis_result(
                job_id=str(job.job_id),
                user_id=str(job.user_id),
                audio_url=str(job.audio_url),
                analysis_result=analysis_result,
                job_description=request_data["job_description"],
                status="completed",
                callback_url=str(job.callback_url),
                questions=request_data.get("questions", []),
            )

            log_info(f"Successfully completed job {job.job_id}")
            return analysis_result

        except Exception as e:
            log_error(f"Failed to process job {job.job_id}: {str(e)}")
            await analysis_repository.update_job_status(str(job.job_id), "failed")

            # Log error for debugging
            await audit_repository.log_error(
                user_id=str(job.user_id),
                job_id=str(job.job_id),
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace="",  # You can add traceback here
                request_data={"audio_url": job.audio_url},
            )
            raise e

    async def _get_job_request_data(self, job: AnalysisResultDB) -> Dict[str, Any]:
        """
        Extract request data from job record.
        You'll need to store the original request data when creating the job.
        For now, this is a placeholder.
        """
        # TODO: You need to store the original request (job_description, questions, etc.)
        # in your database when creating queued jobs
        raw_questions = job.questions
        questions: List[str] = []

        if raw_questions is None:
            questions = []
        elif isinstance(raw_questions, str):
            # Try JSON parse first (e.g. '["q1","q2"]')
            try:
                parsed = json.loads(raw_questions)
                if isinstance(parsed, (list, tuple)):
                    questions = [str(q) for q in parsed]
                else:
                    questions = [str(parsed)]
            except json.JSONDecodeError:
                # Fallback: comma-separated string "q1, q2"
                questions = [q.strip() for q in raw_questions.split(",") if q.strip()]
        elif isinstance(raw_questions, (list, tuple)):
            questions = [str(q) for q in raw_questions]
        else:
            # Any other type -> coerce to single-string list
            questions = [str(raw_questions)]

        return {
            "audio_url": job.audio_url,
            "job_description": job.job_description,
            "questions": questions,
        }

    async def _perform_complete_analysis(
        self, request_data: Dict[str, Any]
    ) -> AnalysisResult:
        """
        Complete analysis pipeline: Transcription + Gemini Analysis
        This properly mixes async I/O and CPU-bound work
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Step 1: Transcription (I/O-bound - external API call)
            log_info(f"Starting transcription for {request_data['audio_url']}")

            if request_data["audio_url"].startswith(("http://", "https://")):
                transcript, processing_time = (
                    await whisper_service.transcribe_audio_url(
                        request_data["audio_url"], language=request_data["language"]
                    )
                )
            else:
                transcript, processing_time = (
                    await whisper_service.transcribe_local_file(
                        request_data["audio_url"]
                    )
                )

            log_info(f"Transcription completed: {len(transcript)} characters")

            # Step 2: Gemini Analysis (Mixed I/O and CPU)
            # The API call is I/O, but response processing might be CPU-intensive
            log_info("Starting Gemini analysis")

            # Run Gemini analysis (it's already async)
            gemini_analysis = await gemini_service.analyze_interview(
                transcript=transcript,
                job_description=request_data["job_description"],
                questions=request_data.get("questions"),
            )

            # Step 3: Calculate total processing time
            total_processing_time = asyncio.get_event_loop().time() - start_time

            # Create final result
            analysis_result = AnalysisResult(
                transcript=transcript,
                technical_score=gemini_analysis["technical_score"],
                communication_score=gemini_analysis["communication_score"],
                confidence_indicators=gemini_analysis["confidence_indicators"],
                key_insights=gemini_analysis["key_insights"],
                processing_time=total_processing_time,
            )

            log_info("Gemini analysis completed successfully")
            return analysis_result

        except Exception as e:
            log_error(f"Analysis pipeline failed: {str(e)}")
            raise e

    async def _send_webhook_notification(
        self, callback_url: str, job_id: str, status: str, error_msg: str = ""
    ):
        """Send webhook notification for job completion"""
        try:
            # You'll need to implement actual webhook sending
            # For now, just log it
            log_info(f"Webhook {callback_url}: Job {job_id} -> {status}")
            if error_msg:
                log_info(f"Webhook error details: {error_msg}")
        except Exception as e:
            log_error(f"Failed to send webhook for job {job_id}: {str(e)}")


# Global processor instance
job_processor = AsyncJobProcessor(max_concurrent_jobs=3)
