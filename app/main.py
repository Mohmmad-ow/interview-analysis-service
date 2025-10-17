from typing import Union
from fastapi import APIRouter, FastAPI, HTTPException

from app.models.response import AnalysisResult
from app.models.request import InterviewAnalysisRequest

app = FastAPI()
