# app/services/webhook_service.py
from datetime import datetime, timezone
from logging import log
from typing import Any, Dict, Optional, Union

import httpx

from app.core.logging import log_info, log_warning
from app.database.repository import WebhookRepository
from app.database.connection import db_manager
from app.models.analysis.response import AnalysisResult


class WebhookService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3

    async def send_webhook(
        self,
        callback_url: str,
        job_id: str,
        status: str,
        result: Union[AnalysisResult, Dict[str, Any]],
        error: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send webhook with full tracking
        Returns delivery status and details
        """

        # Create or get webhook repository
        session = next(db_manager.get_session())
        webhook_repo = WebhookRepository(session)

        # Create delivery record if it doesn't exist
        delivery = await webhook_repo.get_delivery(job_id)
        if not delivery:
            delivery = await webhook_repo.create_delivery_record(
                job_id=job_id, callback_url=callback_url, user_id=user_id
            )

        # Build payload
        payload = self._build_payload(job_id, status, result, error)

        # Store payload in delivery record
        delivery.payload_sent = payload  # type: ignore
        session.commit()

        # Attempt delivery
        attempt = delivery.attempts + 1
        log_info(f"Webhook attempt {attempt} for job {job_id}")

        try:
            response = await self.client.post(
                callback_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "InterviewAnalysisService/1.0",
                    "X-Webhook-Attempt": str(attempt),
                    "X-Webhook-Job-ID": job_id,
                },
            )

            # Get response details
            response_body = response.text if response.content else None

            # Check if successful (2xx status)
            if 200 <= response.status_code < 300:
                # Success!
                await webhook_repo.update_delivery_attempt(
                    job_id=job_id,
                    attempt_number=int(attempt),  # type: ignore
                    status="delivered",
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response_body,
                )

                log_info(f"✅ Webhook delivered for job {job_id}")
                return {
                    "success": True,
                    "status": "delivered",
                    "attempt": attempt,
                    "response_code": response.status_code,
                }
            else:
                # Non-2xx response
                error_msg = f"Client returned {response.status_code}"
                new_status = "retrying" if int(attempt) < self.max_retries else "failed"  # type: ignore

                await webhook_repo.update_delivery_attempt(
                    job_id=job_id,
                    attempt_number=int(attempt),  # type: ignore
                    status=new_status,
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response_body,
                    error_message=error_msg,
                    error_type="http_error",
                )

                log_warning(
                    f"⚠️ Webhook returned {response.status_code} for job {job_id}"
                )

        except httpx.TimeoutException:
            error_msg = "Connection timeout"
            new_status = "retrying" if int(attempt) < self.max_retries else "failed"  # type: ignore

            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=int(attempt),  # type: ignore
                status=new_status,
                error_message=error_msg,
                error_type="timeout",
            )

        except httpx.NetworkError as e:
            error_msg = str(e)
            new_status = "retrying" if int(attempt) < self.max_retries else "failed"  # type: ignore

            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=int(attempt),  # type: ignore
                status=new_status,
                error_message=error_msg,
                error_type="network_error",
            )

        except Exception as e:
            error_msg = str(e)
            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=int(attempt),  # type: ignore
                status="failed",
                error_message=error_msg,
                error_type="unknown_error",
            )

        return {
            "success": False,
            "status": new_status,
            "attempt": attempt,
            "next_retry": (
                delivery.next_retry_at.isoformat()
                if delivery.next_retry_at is not None
                else None
            ),
        }

    async def get_delivery_status(self, job_id: str) -> Optional[Dict]:
        """Get webhook delivery status for a job"""
        session = next(db_manager.get_session())
        webhook_repo = WebhookRepository(session)

        delivery = await webhook_repo.get_delivery(job_id)
        if not delivery:
            return None

        return {
            "job_id": delivery.job_id,
            "status": delivery.status,
            "attempts": delivery.attempts,
            "max_attempts": delivery.max_attempts,
            "created_at": (
                delivery.created_at.isoformat()
                if delivery.created_at is not None
                else None
            ),
            "last_attempt": (
                delivery.last_attempt.isoformat()
                if delivery.last_attempt is not None
                else None
            ),
            "delivered_at": (
                delivery.delivered_at.isoformat()
                if delivery.delivered_at is not None
                else None
            ),
            "next_retry": (
                delivery.next_retry_at.isoformat()
                if delivery.next_retry_at is not None
                else None
            ),
            "response_status": delivery.response_status,
            "error_message": delivery.error_message,
            "error_type": delivery.error_type,
            "callback_url": delivery.callback_url,
        }

    def _build_payload(self, job_id: str, status: str, result=None, error=None):
        """Build webhook payload"""
        result_data = result
        if result and not isinstance(result, dict):
            if hasattr(result, "dict"):  # Pydantic v1
                result_data = result.dict()
            elif hasattr(result, "model_dump"):  # Pydantic v2
                result_data = result.model_dump()
            else:
                result_data = vars(result)  # Standard Python object

        return {
            "job_id": job_id,
            "status": status,
            "service": "interview-analysis",
            "timestamp": datetime.utcnow().isoformat(),
            "result": result_data,
            "error": {"message": error} if error else None,
        }


# Create global instance
webhook_service = WebhookService()
