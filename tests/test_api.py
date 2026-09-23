from fastapi.testclient import TestClient

from app import queue_client
from app.api import app
from app.handlers import REQUEST_MESSAGE_TYPE, settings


def test_ping():
    client = TestClient(app)
    resp = client.get('/ping')
    assert resp.status_code == 200
    assert resp.json() == {'response': 'pong'}


def test_create_reports_enqueues_message(moto_aws):
    client = TestClient(app)
    body = {
        'requests': [
            {'program': 'PROG', 'request_number': 'REQ1', 'item_count': 10, 'recipients': ['a@example.com']},
        ]
    }
    resp = client.post('/reports', json=body)

    assert resp.status_code == 200
    assert resp.json() == {'status': 'IN PROGRESS'}

    records = queue_client.receive_messages(settings.queue_name, max_messages=10)
    assert len(records) == 1
    assert queue_client.message_type(records[0]) == REQUEST_MESSAGE_TYPE
