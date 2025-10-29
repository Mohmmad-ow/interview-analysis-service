import sys
import os
from loguru import logger
from app.config import settings


class FallbackLogger:
    """
    Simple fallback logger that always works
    Used if Loguru fails to initialize
    """

    def debug(self, message, **kwargs):
        print(f"🔍 [DEBUG] {message}", flush=True)

    def info(self, message, **kwargs):
        print(f"ℹ️  [INFO] {message}", flush=True)

    def warning(self, message, **kwargs):
        print(f"⚠️  [WARN] {message}", flush=True)

    def error(self, message, **kwargs):
        print(f"❌ [ERROR] {message}", flush=True, file=sys.stderr)

    def critical(self, message, **kwargs):
        print(f"💥 [CRITICAL] {message}", flush=True, file=sys.stderr)


def setup_logging():
    """
    Configure Loguru with proper error handling
    """
    try:
        # Remove default handler
        logger.remove()

        # Development console logging
        logger.add(
            sys.stderr,
            level=settings.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
            backtrace=True,
            diagnose=settings.DEBUG,
        )

        print("✅ Loguru configured successfully!")
        return logger

    except Exception as e:
        print(f"❌ Loguru setup failed: {e}. Using fallback logger.")
        return FallbackLogger()


# Initialize logger - this will NEVER be None
log = setup_logging()


# Helper function for structured logging that always works
def log_with_context(level: str, message: str, **context):
    """
    Safe logging with context that works with both Loguru and fallback
    """
    try:
        # runtime check for Loguru's logger which exposes `bind`
        if hasattr(log, "bind") and callable(
            getattr(log, "bind")
        ):  # It's a Loguru logger
            log.bind(**context).log(level, message)  # type: ignore
        else:  # It's the fallback logger
            context_str = " ".join([f"{k}={v}" for k, v in context.items()])
            full_message = f"{message} - {context_str}" if context_str else message
            # call the appropriate fallback method if it exists, otherwise print
            handler = getattr(log, level, None)
            if callable(handler):
                handler(full_message)
            else:
                print(full_message)
    except Exception as e:
        # Ultimate fallback - just print
        print(f"🚨 LOGGING FAILED: {message} - Error: {e}")


# Convenience methods
def log_info(message: str, **context):
    log_with_context("info", message, **context)


def log_error(message: str, **context):
    log_with_context("error", message, **context)


def log_warning(message: str, **context):
    log_with_context("warning", message, **context)


def log_debug(message: str, **context):
    log_with_context("debug", message, **context)
