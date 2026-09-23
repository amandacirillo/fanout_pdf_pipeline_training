import json

from app import handlers, queue_client, storage_client


def _drain_and_run_workers(queue_name: str):
    """Test helper: pull worker messages off the queue and run them
    synchronously, standing in for the real Lambda SQS event source mapping.
    """
    records = queue_client.receive_messages(queue_name, max_messages=10)
    for record in records:
        message = json.loads(record['body'])
        msg_type = queue_client.message_type(record)
        assert msg_type == handlers.WORKER_MESSAGE_TYPE
        handlers.handle_worker(message)
    return len(records)


def test_handle_request_dispatch_only(moto_aws):
    message = {'program': 'PROG', 'requestNumber': 'REQ1', 'itemCount': 12, 'recipients': []}
    result = handlers.handle_request(message, poll=False)

    assert result['status'] == 'DISPATCHED'
    assert result['workerCount'] == 3  # 12 items / 5 per worker (patched), ceil -> 3

    dispatched = _drain_and_run_workers(handlers.settings.queue_name)
    assert dispatched == 3
    for i in range(3):
        assert storage_client.exists(storage_client.worker_output_key('PROG', 'REQ1', i))


def test_handle_request_full_flow_with_polling(moto_aws):
    """End-to-end: dispatch workers, run them (simulating the real SQS
    trigger firing before the dispatcher's poll loop times out), then let the
    dispatcher's own poll-and-combine step finish."""
    import threading
    import time

    message = {'program': 'PROG', 'requestNumber': 'REQ2', 'itemCount': 8, 'recipients': ['someone@example.com']}

    def run_workers_shortly_after_dispatch():
        time.sleep(0.05)
        # Give the dispatcher a moment to send worker messages first.
        for _ in range(5):
            if _drain_and_run_workers(handlers.settings.queue_name):
                break
            time.sleep(0.05)

    worker_thread = threading.Thread(target=run_workers_shortly_after_dispatch)
    worker_thread.start()

    result = handlers.handle_request(message, poll=True)
    worker_thread.join()

    assert result['status'] == 'COMPLETE'
    assert storage_client.exists(storage_client.combined_output_key('PROG', 'REQ2'))

    # Recipients were provided, so an alert message should have been queued.
    alerts = queue_client.receive_messages(handlers.settings.alert_queue_name, max_messages=10)
    assert len(alerts) == 1
    alert_body = json.loads(alerts[0]['body'])
    assert alert_body['subject'].startswith('Report COMPLETE')


def test_handle_request_times_out_and_sends_error_alert(moto_aws, monkeypatch):
    object.__setattr__(handlers.settings, 'poll_timeout_seconds', 0.1)
    message = {'program': 'PROG', 'requestNumber': 'REQ3', 'itemCount': 5, 'recipients': ['someone@example.com']}

    # Deliberately never run the workers, so the dispatcher's poll times out.
    result = handlers.handle_request(message, poll=True)

    assert result['status'] == 'ERROR'
    alerts = queue_client.receive_messages(handlers.settings.alert_queue_name, max_messages=10)
    assert len(alerts) == 1
    assert 'ERROR' in json.loads(alerts[0]['body'])['subject']
