"""FastAPI app: a single fire-and-forget endpoint that enqueues report
requests and returns immediately. The actual report generation happens
asynchronously via the SQS-driven handlers in handlers.py."""
import logging

from fastapi import FastAPI

from app import handlers
from app.schemas import ReportRequestBody, ReportResponse

logging.basicConfig(level=logging.INFO)

app = FastAPI(title='Fan-out PDF Pipeline API')


@app.get('/ping')
def ping():
    return {'response': 'pong'}


@app.post('/reports', response_model=ReportResponse)
def create_reports(body: ReportRequestBody) -> dict:
    for report_request in body.requests:
        handlers.enqueue_request(
            program=report_request.program,
            request_number=report_request.request_number,
            item_count=report_request.item_count,
            recipients=report_request.recipients,
        )
    return {'status': 'IN PROGRESS'}
