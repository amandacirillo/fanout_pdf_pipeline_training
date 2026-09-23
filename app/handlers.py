"""Core fan-out / fan-in orchestration logic.

Flow:
  1. `handle_request` (dispatcher) splits `item_count` into N worker chunks,
     sends N 'worker' messages, then polls S3 until every worker's output
     shows up.
  2. `handle_worker` (worker) renders its chunk's PDF and uploads it.
  3. Once all workers are done, the dispatcher merges + paginates the PDFs
     and sends a completion alert.

In production this dispatcher poll-and-wait loop runs inside a single Lambda
invocation (with a correspondingly long Lambda timeout) -- simple to build,
but it ties up a Lambda for the full duration of the slowest worker instead
of using a callback/event-driven design. See the README exercises for the
trade-off against Step Functions.
"""
import datetime
import json
import time
from typing import Any, Callable, Dict, List

import structlog

from app import pdf_utils, queue_client, storage_client
from app.settings import settings

logger = structlog.get_logger(__name__)

REQUEST_MESSAGE_TYPE = 'reports.request'
WORKER_MESSAGE_TYPE = 'reports.worker'
SOURCE = 'fanout-pdf-pipeline'


def datetime_for_alert(dtime: datetime.datetime) -> str:
    """Format a datetime the way a downstream Java alert service expects:
    millisecond precision plus a trailing 'Z'. Python's default %f gives
    microseconds, so trim to 3 digits before appending Z."""
    time_str = dtime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
    return f'{time_str}Z'


def enqueue_request(program: str, request_number: str, item_count: int, recipients: List[str]) -> str:
    """Called from the API layer: fire-and-forget enqueue, no waiting for completion here."""
    message = {
        'program': program,
        'requestNumber': request_number,
        'itemCount': item_count,
        'recipients': recipients,
    }
    return queue_client.send_message(settings.queue_name, message, REQUEST_MESSAGE_TYPE, SOURCE)


def handle_worker(message: Dict[str, Any]) -> None:
    """Render this worker's chunk and upload it. No return value -- the
    dispatcher discovers completion by polling S3, not via a response here."""
    program = message['program']
    request_number = message['requestNumber']
    worker_number = message['workerNumber']
    start_item = message['startItem']
    end_item = message['endItem']

    logger.info('worker starting', program=program, request_number=request_number, worker=worker_number)
    pdf_bytes = pdf_utils.make_placeholder_pdf(
        title=f'{program} / {request_number} (items {start_item}-{end_item})',
        item_count=end_item - start_item + 1,
    )
    key = storage_client.worker_output_key(program, request_number, worker_number)
    storage_client.put_bytes(key, pdf_bytes)
    logger.info('worker finished', key=key)


def _worker_chunks(item_count: int) -> List[tuple]:
    """Split item_count into (start, end) ranges of at most items_per_worker each."""
    chunks = []
    start = 1
    while start <= item_count:
        end = min(item_count, start + settings.items_per_worker - 1)
        chunks.append((start, end))
        start = end + 1
    return chunks or [(0, 0)]  # always produce at least one worker/page


def handle_request(message: Dict[str, Any], poll: bool = True) -> Dict[str, Any]:
    """Dispatcher: fan out worker messages, then (optionally) wait for and
    merge their output. `poll=False` is used by tests/local runs that drive
    workers synchronously instead of waiting on a real queue.
    """
    program = message['program']
    request_number = message['requestNumber']
    item_count = message['itemCount']
    recipients = message.get('recipients', [])

    storage_client.ensure_bucket()
    chunks = _worker_chunks(item_count)

    for key in [storage_client.worker_output_key(program, request_number, i) for i in range(len(chunks))]:
        storage_client.delete_if_exists(key)
    storage_client.delete_if_exists(storage_client.combined_output_key(program, request_number))

    for worker_number, (start_item, end_item) in enumerate(chunks):
        worker_message = {
            'program': program,
            'requestNumber': request_number,
            'workerNumber': worker_number,
            'startItem': start_item,
            'endItem': end_item,
        }
        queue_client.send_message(settings.queue_name, worker_message, WORKER_MESSAGE_TYPE, SOURCE)

    if not poll:
        return {'status': 'DISPATCHED', 'workerCount': len(chunks)}

    return _wait_and_combine(program, request_number, len(chunks), recipients)


def _wait_and_combine(program: str, request_number: str, worker_count: int, recipients: List[str]) -> Dict[str, Any]:
    keys = [storage_client.worker_output_key(program, request_number, i) for i in range(worker_count)]
    deadline = time.monotonic() + settings.poll_timeout_seconds
    missing = set(keys)
    while missing and time.monotonic() < deadline:
        missing = {key for key in missing if not storage_client.exists(key)}
        if missing:
            time.sleep(settings.poll_interval_seconds)

    if missing:
        status = {'status': 'ERROR', 'errors': [f'Timed out waiting for {len(missing)} worker(s)']}
        _send_alert(program, request_number, status, recipients)
        return status

    pdf_bytes_list = [storage_client.get_bytes(key) for key in keys]
    combined = pdf_utils.merge_pdfs(pdf_bytes_list)
    numbered = pdf_utils.add_page_numbers(combined)
    combined_key = storage_client.combined_output_key(program, request_number)
    storage_client.put_bytes(combined_key, numbered)

    status = {'status': 'COMPLETE', 'outputKey': combined_key}
    _send_alert(program, request_number, status, recipients)
    return status


def _send_alert(program: str, request_number: str, status: Dict[str, Any], recipients: List[str]) -> None:
    if not recipients:
        return
    if status['status'] == 'COMPLETE':
        subject = f'Report COMPLETE - {program} - {request_number}'
    else:
        subject = f'Report ERROR - {program} - {request_number} - {",".join(status.get("errors", []))}'
    alert_message = {
        'sourceName': 'FanoutPdfPipeline',
        'alertDate': datetime_for_alert(datetime.datetime.now(datetime.timezone.utc)),
        'program': program,
        'requestNumber': request_number,
        'subject': subject,
        'recipients': recipients,
    }
    queue_client.send_message(settings.alert_queue_name, alert_message, 'reports.alert', SOURCE)


SQS_HANDLER_TYPE_MAP: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    REQUEST_MESSAGE_TYPE: handle_request,
    WORKER_MESSAGE_TYPE: handle_worker,
}


def sqs_handler(records: List[Dict[str, Any]]) -> None:
    """Dispatch each record to the right handler based on its `type` message attribute.

    A single queue/handler routes by type instead of using one queue per
    message kind -- fewer queues and Lambda triggers to manage, at the cost of
    needing this routing table.
    """
    for record in records:
        message = json.loads(record['body'])
        msg_type = queue_client.message_type(record)
        handler = SQS_HANDLER_TYPE_MAP.get(msg_type or '')
        if handler is None:
            logger.error('unexpected message type', msg_type=msg_type)  # noqa: E501
            continue
        handler(message)
