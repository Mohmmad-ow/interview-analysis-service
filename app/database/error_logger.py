import traceback
from typing import Optional, Dict, Any
from app.database.audit_logger import audit_logger


class ErrorLogger:
    @staticmethod
    async def capture_exception(
        user_id: Optional[str] = None,
        job_id: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        custom_message: Optional[str] = None,
    ):
        """
        Capture and log exceptions with full context
        """
        import sys

        exc_type, exc_value, exc_traceback = sys.exc_info()

        error_details = {
            "error_type": exc_type.__name__ if exc_type else "Unknown",
            "error_message": str(exc_value),
            "stack_trace": traceback.format_exc(),
            "custom_message": custom_message,
        }

        # Log to error_logs table
        await audit_logger.log_error(
            user_id=user_id,
            job_id=job_id,
            error_type=error_details["error_type"],
            error_message=error_details["error_message"],
            stack_trace=error_details["stack_trace"],
            request_data=request_data,
        )

        return error_details


# Global error logger
error_logger = ErrorLogger()
