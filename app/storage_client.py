"""Thin wrapper around boto3 S3, used as the 'worker finished' signal.

Workers don't talk back to the dispatcher directly -- they just write their
output to a known S3 key. The dispatcher polls for that key's existence. This
trades a little latency (the poll interval) for a much simpler architecture
than a callback queue or Step Functions callback task. See the README for
when that trade-off stops being worth it.
"""
import boto3
from botocore.exceptions import ClientError

from app.settings import settings


def _client():
    return boto3.client('s3', region_name=settings.aws_region)


def ensure_bucket() -> None:
    client = _client()
    try:
        client.head_bucket(Bucket=settings.bucket)
    except ClientError:
        if settings.aws_region == 'us-east-1':
            client.create_bucket(Bucket=settings.bucket)
        else:
            client.create_bucket(
                Bucket=settings.bucket,
                CreateBucketConfiguration={'LocationConstraint': settings.aws_region},
            )


def put_bytes(key: str, data: bytes) -> None:
    _client().put_object(Bucket=settings.bucket, Key=key, Body=data)


def get_bytes(key: str) -> bytes:
    return _client().get_object(Bucket=settings.bucket, Key=key)['Body'].read()


def exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.bucket, Key=key)
        return True
    except ClientError:
        return False


def delete_if_exists(key: str) -> None:
    try:
        _client().delete_object(Bucket=settings.bucket, Key=key)
    except ClientError:
        pass


def worker_output_key(program: str, request_number: str, worker_number: int) -> str:
    return f'{program}/{request_number}/worker-{worker_number}.pdf'


def combined_output_key(program: str, request_number: str) -> str:
    return f'{program}/{request_number}/combined.pdf'
