"""Thin wrapper around boto3 SQS so the rest of the app never touches boto3
directly. In tests this talks to a moto-mocked queue; in Lambda it talks to
the real one -- same code path either way, which is the point.
"""
import json
import uuid
from typing import Any, Dict, List, Optional

import boto3

from app.settings import settings


def _client():
    return boto3.client('sqs', region_name=settings.aws_region)


def get_or_create_queue_url(queue_name: str) -> str:
    """Look up a queue's URL, creating it if it doesn't exist yet.

    Real deployments create the queue via CDK/CloudFormation ahead of time;
    this fallback just keeps local/dev usage and tests simple.
    """
    client = _client()
    try:
        return client.get_queue_url(QueueName=queue_name)['QueueUrl']
    except client.exceptions.QueueDoesNotExist:
        return client.create_queue(QueueName=queue_name)['QueueUrl']


def send_message(queue_name: str, message: Dict[str, Any], message_type: str, source: str) -> str:
    """Send one JSON message with a `type` attribute other handlers use for routing.

    Using a single queue with a `type` attribute (rather than one queue per
    message kind) keeps infra simple -- one queue, one Lambda trigger -- while
    still letting the handler dispatch to different logic per message kind.
    """
    queue_url = get_or_create_queue_url(queue_name)
    correlation_id = f'{source}/{uuid.uuid4().hex}'
    _client().send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message),
        MessageAttributes={
            'type': {'StringValue': message_type, 'DataType': 'String'},
            'source': {'StringValue': source, 'DataType': 'String'},
            'correlationId': {'StringValue': correlation_id, 'DataType': 'String'},
        },
    )
    return correlation_id


def receive_messages(queue_name: str, max_messages: int = 10) -> List[Dict[str, Any]]:
    """Poll for up to `max_messages` and delete them once returned.

    A real Lambda-SQS trigger delivers records directly to the handler and
    manages deletion for you; this helper exists so the same handler code can
    also be driven by a local polling loop (see the README's "running locally"
    section) or by tests, without a Lambda event source mapping.
    """
    queue_url = get_or_create_queue_url(queue_name)
    resp = _client().receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        MessageAttributeNames=['All'],
        WaitTimeSeconds=0,
    )
    messages = resp.get('Messages', [])
    records = []
    for msg in messages:
        records.append({
            'body': msg['Body'],
            'messageAttributes': {
                key: {'stringValue': val['StringValue']}
                for key, val in msg.get('MessageAttributes', {}).items()
            },
            'receiptHandle': msg['ReceiptHandle'],
        })
        _client().delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
    return records


def message_type(record: Dict[str, Any]) -> Optional[str]:
    return record.get('messageAttributes', {}).get('type', {}).get('stringValue')
