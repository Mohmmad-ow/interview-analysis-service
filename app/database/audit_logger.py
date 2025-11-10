from sqlalchemy.orm import Session
from app.database.models import AuditLog, ErrorLog
from app.database.connection import db_manager
from typing import Optional, Dict, Any
from app.core.logging import logger
from contextlib import contextmanager
import time


class AuditLogger:
    @staticmethod
    async def log_action(
        user_id: str,
        action: str,
        resource: Optional[str] = None,
        success: bool = True,
        processing_time: Optional[float] = None,
        error_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Log user actions to audit_logs table
        """
        try:
            session = db_manager.SessionLocal()

            audit_entry = AuditLog(
                user_id=user_id,
                action=action,
                resource=resource,
                success=success,
                processing_time=processing_time,
                error_type=error_type,
                metadata=metadata or {},
            )

            session.add(audit_entry)
            session.commit()

            logger.info(f"Audit logged: {action} by {user_id}")

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Don't raise - audit failures shouldn't break main functionality

    @staticmethod
    async def log_error(
        user_id: Optional[str],
        job_id: Optional[str],
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log errors to error_logs table
        """
        try:
            session = db_manager.SessionLocal()

            error_entry = ErrorLog(
                user_id=user_id,
                job_id=job_id,
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
                request_data=request_data or {},
            )

            session.add(error_entry)
            session.commit()
            logger.error(f"Error logged: {error_type} - {error_message}")

        except Exception as e:
            logger.error(f"Failed to write error log: {e}")


@contextmanager
def audit_traffic(user_id: str, action: str, resource: str):
    """
    Context manager for automatic audit logging with timing
    """
    start_time = time.time()
    success = True
    error_type = None

    try:
        yield
    except Exception as e:
        success = False
        error_type = type(e).__name__
        raise
    finally:
        processing_time = time.time() - start_time
        # Fire and forget - don't wait for audit log
        import asyncio

        asyncio.create_task(
            AuditLogger.log_action(
                user_id=user_id,
                action=action,
                resource=resource,
                success=success,
                processing_time=processing_time,
                error_type=error_type,
            )
        )


# Global instance
audit_logger = AuditLogger()
