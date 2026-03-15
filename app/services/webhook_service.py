# app/services/webhook_service.py
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
import logging
import httpx

from app.database.repository import webhook_repository as webhook_repo
from app.database.connection import db_manager
from app.models.analysis.response import DocumentAnalysisResult

log = logging.getLogger(__name__)


class DocumentWebhookService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3
        self.service_name = "document-analysis"

    async def send_webhook(
        self,
        callback_url: str,
        job_id: str,
        status: str,
        go_job_posting_id: str,
        result: Optional[DocumentAnalysisResult] = None,
        error: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send webhook with full tracking
        Returns delivery status and details
        """
        # Get session and repository
        session = next(db_manager.get_session())

        # Create or get delivery record
        delivery = await webhook_repo.get_delivery(job_id)
        if not delivery:
            delivery = await webhook_repo.create_delivery_record(
                job_id=job_id, callback_url=callback_url, user_id=user_id
            )

        # Build payload
        payload = self._build_payload(job_id, status,go_job_posting_id,result, error)
        print(f"webhook payload: {payload}")
        
        # Store payload in delivery record
        delivery.payload_sent = payload # type: ignore
        session.commit()

        # Attempt delivery
        attempt = delivery.attempts + 1
        log.info(f"📤 Webhook attempt {attempt} for job {job_id}")

        try:
            response = await self.client.post(
                callback_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"{self.service_name}/1.0",
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
                    attempt_number=int(attempt), # type: ignore
                    status="delivered",
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response_body,
                )

                log.info(f"✅ Webhook delivered for job {job_id}")
                return {
                    "success": True,
                    "status": "delivered",
                    "attempt": attempt,
                    "response_code": response.status_code,
                }
            else:
                # Non-2xx response
                error_msg = f"Client returned {response.status_code}"
                new_status = "retrying" if attempt < self.max_retries else "failed" # type: ignore

                await webhook_repo.update_delivery_attempt(
                    job_id=job_id,
                    attempt_number=attempt, # type: ignore
                    status=new_status,
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response_body,
                    error_message=error_msg,
                    error_type="http_error",
                )

                log.warning(
                    f"⚠️ Webhook returned {response.status_code} for job {job_id}"
                )

        except httpx.TimeoutException:
            error_msg = "Connection timeout"
            new_status = "retrying" if attempt < self.max_retries else "failed" # type: ignore

            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=attempt, # type: ignore
                status=new_status,
                error_message=error_msg,
                error_type="timeout",
            )
            log.warning(f"⏱️ Webhook timeout for job {job_id}")

        except httpx.NetworkError as e:
            error_msg = str(e)
            new_status = "retrying" if attempt < self.max_retries else "failed" # type: ignore

            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=attempt, # type: ignore
                status=new_status,
                error_message=error_msg,
                error_type="network_error",
            )
            log.warning(f"🌐 Webhook network error for job {job_id}: {error_msg}")

        except Exception as e:
            error_msg = str(e)
            await webhook_repo.update_delivery_attempt(
                job_id=job_id,
                attempt_number=attempt, # type: ignore
                status="failed",
                error_message=error_msg,
                error_type="unknown_error",
            )
            log.error(f"❌ Webhook unknown error for job {job_id}: {error_msg}")
        finally:
            session.close()
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

    def _build_payload(
        self, 
        job_id: str, 
        status: str, 
        go_job_id: str, 
        result: Optional[DocumentAnalysisResult] = None, 
        error: Optional[str] = None
    ):
        """Build webhook payload safely"""
        
        # Safely extract resume_url
        resume_url = ""
        if result and hasattr(result, "resume_url") and result.resume_url:
            resume_url = result.resume_url

        payload = {
            "job_id": job_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "metadata": {
                "go_job_posting_id": go_job_id,
                "resume_url": resume_url
            }
        }

        if status == "completed" and result:
            # Use model_dump for Pydantic v2 or dict() for v1
            if hasattr(result, "model_dump"):
                payload["result"] = result.model_dump()
            else:
                payload["result"] = result.dict()
                
        elif status == "failed" and error:
            payload["error"] = {
                "message": error,
                "type": "processing_error",
            }

        return payload


# Global instance
document_webhook_service = DocumentWebhookService()