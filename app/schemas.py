"""Request/response models for the API layer."""
from typing import List

from pydantic import BaseModel


class ReportRequest(BaseModel):
    program: str
    request_number: str
    item_count: int
    recipients: List[str] = []


class ReportRequestBody(BaseModel):
    requests: List[ReportRequest]


class ReportResponse(BaseModel):
    status: str
