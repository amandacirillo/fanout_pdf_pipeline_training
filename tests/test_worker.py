from app import handlers, storage_client


def test_handle_worker_uploads_pdf(moto_aws):
    storage_client.ensure_bucket()
    message = {
        'program': 'PROG',
        'requestNumber': 'REQ1',
        'workerNumber': 0,
        'startItem': 1,
        'endItem': 5,
    }
    handlers.handle_worker(message)

    key = storage_client.worker_output_key('PROG', 'REQ1', 0)
    assert storage_client.exists(key)
    assert len(storage_client.get_bytes(key)) > 0


def test_worker_chunks_split_by_items_per_worker():
    # items_per_worker patched to 5 by the fast_polling fixture
    chunks = handlers._worker_chunks(12)
    assert chunks == [(1, 5), (6, 10), (11, 12)]


def test_worker_chunks_zero_items_produces_one_empty_chunk():
    assert handlers._worker_chunks(0) == [(0, 0)]
