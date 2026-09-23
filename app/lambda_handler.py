"""AWS Lambda entrypoint. Routes SQS events to the fan-out/fan-in handlers,
and everything else (HTTP via API Gateway/ALB) to the FastAPI app via Mangum.
"""
from mangum import Mangum

from app.api import app
from app.handlers import sqs_handler

asgi_handler = Mangum(app, lifespan='off')


def handler(event, context):
    if 'Records' in event:
        records = [r for r in event['Records'] if r.get('eventSource') == 'aws:sqs']
        sqs_handler(records)
        return {'processed': len(records)}
    return asgi_handler(event, context)
