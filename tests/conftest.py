import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """Speed up the dispatcher's wait-for-workers poll loop in tests.

    `settings` is a frozen dataclass singleton imported by reference
    everywhere, so patch its fields in place with object.__setattr__ instead
    of re-importing the module (which wouldn't affect already-imported
    references in handlers.py etc.).
    """
    from app.settings import settings

    original = (settings.poll_interval_seconds, settings.poll_timeout_seconds, settings.items_per_worker)
    # A zero-second interval turns the dispatcher's poll loop into a tight
    # busy-loop that can starve the worker thread of the GIL on constrained
    # CI runners, causing spurious timeouts. A small nonzero interval still
    # keeps tests fast while letting the worker thread actually run.
    object.__setattr__(settings, 'poll_interval_seconds', 0.02)
    object.__setattr__(settings, 'poll_timeout_seconds', 10.0)
    object.__setattr__(settings, 'items_per_worker', 5)
    yield
    object.__setattr__(settings, 'poll_interval_seconds', original[0])
    object.__setattr__(settings, 'poll_timeout_seconds', original[1])
    object.__setattr__(settings, 'items_per_worker', original[2])


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_SECURITY_TOKEN', 'testing')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')


@pytest.fixture
def moto_aws(aws_credentials):
    with mock_aws():
        yield boto3
