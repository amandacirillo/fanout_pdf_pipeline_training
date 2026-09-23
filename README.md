# Fan-out / Fan-in PDF Pipeline Training

A training example of an async, fire-and-forget reporting pipeline built on FastAPI + Lambda +
SQS + S3: one endpoint enqueues a request, a dispatcher fans work out to N worker invocations,
and results are merged and paginated once every worker finishes. This mirrors a real pattern for
generating many small PDF reports in parallel and combining them into one deliverable.

## Architecture

```
        POST /reports                          SQS (single queue, routed by `type`)
  client ───────────────▶ FastAPI (Lambda) ───▶ ┌─────────────────────────────┐
                          returns "IN PROGRESS"  │  type=reports.request        │
                                                 │  type=reports.worker (xN)    │
                                                 └──────────────┬──────────────┘
                                                                │
                     ┌──────────────────────────────────────────┴───────────────────────┐
                     ▼                                                                  ▼
             dispatcher handler                                                 worker handler
       (splits item_count into chunks,                                    (renders one chunk's
        sends N worker messages, then                                      PDF, uploads to S3)
        polls S3 for all N outputs)
                     │
                     ▼
        merge worker PDFs + stamp page numbers (pypdf + reportlab)
                     │
                     ▼
        upload combined.pdf to S3  +  send an alert message (SQS)
```

Everything -- the HTTP API and both SQS message handlers -- runs from one Lambda
(`app/lambda_handler.py`), which is a common way to keep a single deployable unit while still
handling multiple event source types.

## Why poll S3 instead of a callback?

The dispatcher doesn't get a signal when a worker finishes -- it just polls S3 with
`head_object` until every expected key exists (or it times out). That's simpler to build than a
callback queue or a Step Functions
[callback task token](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token),
but it means:

- the dispatcher Lambda has to stay alive (and billed) for the whole wait, so its timeout has to
  exceed the slowest expected worker run
- there's no visual execution graph, retry policy, or per-step history the way Step Functions
  gives you (see the separate `stepfunctions_training` repo for that alternative)
- polling interval trades latency for SQS/API request volume

This is a reasonable choice for a handful of short-lived workers. It stops being a good choice
once workers take minutes, may retry independently, or the workflow needs branching/error
recovery -- that's when a Step Functions Map state or an event-driven "last one out turns off the
lights" DynamoDB counter pattern usually wins.

## Single queue, routed by message type

`app/handlers.py`'s `SQS_HANDLER_TYPE_MAP` routes each message to a handler based on its `type`
message attribute, rather than using one queue per message kind. Fewer queues and Lambda event
source mappings to manage, at the cost of a routing table and the requirement that all message
types share one visibility timeout / DLQ policy.

## Running locally

```bash
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.api:app --reload
# in another terminal:
curl -X POST localhost:8000/reports -H "content-type: application/json" \
  -d '{"requests": [{"program": "DEMO", "request_number": "1", "item_count": 12, "recipients": []}]}'
```

By default this talks to whatever AWS credentials/region are in your environment. For fully
local development without touching real AWS, run the test suite instead (it uses
[moto](https://github.com/getmoto/moto) to mock SQS and S3 in-process) or point `boto3` at
[LocalStack](https://localstack.cloud/).

## Tests

```bash
pytest -v
```

`tests/conftest.py`'s `moto_aws` fixture mocks SQS + S3 for the whole test; `fast_polling`
shrinks the poll interval/timeout/chunk size so tests run in milliseconds instead of the
production defaults.

## Tag-driven deploys & image scanning

`infra/cdk/` is a trimmed CDK app illustrating two patterns from the original production
pipeline (not wired to a real CI provider here -- adapt `.github/workflows/tests.yml` or add a
deploy job for your own CI):

1. **Per-environment config resolved by name** (`lib/environment.ts`): a small lookup table of
   account/region/tuning values per environment, selected by a `DEPLOY_ENV_NAME` variable. In the
   original pipeline that name came from parsing a structured git tag like
   `01_02_2024_dev_stack_reports_abc123` with a regex, so a single push-a-tag action could target
   dev/stg/prod without maintaining separate pipeline definitions per environment.
2. **Vulnerability scanning as a deploy gate**: before promoting a build, the real pipeline waited
   for `aws ecr describe-image-scan-findings` to reach an `ACTIVE` status on the freshly pushed
   image, then failed the pipeline if any `CRITICAL` findings were present. The CI workflow here
   includes a lightweight illustrative version using `safety` against `requirements.txt`.

## Exercises

1. **Replace the poll loop with a completion counter.** Instead of polling S3, have each worker
   decrement a counter (e.g. in DynamoDB) and have the *last* worker to finish trigger the merge
   step itself. Compare the code and cost/latency trade-offs against polling.
2. **Add idempotency.** If the same worker message is delivered twice (SQS's at-least-once
   delivery), `handle_worker` will just re-render and re-upload the same key -- harmless here,
   but not every operation is naturally idempotent. Add a guard (e.g. skip if the key already
   exists) and a test for it.
3. **Add a dead-letter queue test.** Simulate a worker that raises an exception and verify your
   understanding of what SQS does with a message after `maxReceiveCount` failed attempts (see
   `DeadLetterQueue` in `lib/stack.ts`).
4. **Parametrize the environment lookup.** Extend `lib/environment.ts` to load values from
   AWS Systems Manager Parameter Store / Secrets Manager instead of a hardcoded map, and discuss
   why that matters for a real multi-account deployment.
5. **Migrate to Step Functions.** Sketch (or build, using ideas from `stepfunctions_training`) a
   Step Functions Map state version of this same dispatcher/worker flow, and compare operational
   visibility and cost against the polling Lambda here.
