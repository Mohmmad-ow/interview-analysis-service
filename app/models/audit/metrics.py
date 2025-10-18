from datetime import datetime
from typing import Dict
from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, bool]


class Metrics(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_processing_time: float
    active_jobs: int
