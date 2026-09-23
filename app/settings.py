"""Centralized configuration, read from environment variables.

Nothing here is a real secret -- this mirrors a common pattern where a settings
module gives every other module one place to read config from, instead of
scattering os.environ.get() calls throughout the codebase.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    aws_region: str = os.environ.get('AWS_REGION', 'us-east-1')
    bucket: str = os.environ.get('BUCKET', 'reports-dev-bucket')
    queue_name: str = os.environ.get('QUEUE_NAME', 'reports-dev-queue')
    alert_queue_name: str = os.environ.get('ALERT_QUEUE_NAME', 'alerts-dev-queue')
    items_per_worker: int = int(os.environ.get('ITEMS_PER_WORKER', '25'))
    poll_interval_seconds: float = float(os.environ.get('POLL_INTERVAL_SECONDS', '5'))
    poll_timeout_seconds: float = float(os.environ.get('POLL_TIMEOUT_SECONDS', '300'))


settings = Settings()
