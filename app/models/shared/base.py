from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response model."""

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
