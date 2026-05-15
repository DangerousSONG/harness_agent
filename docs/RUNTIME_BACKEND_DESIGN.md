# Runtime Backend Design

## Purpose

The Runtime Backend layer separates manager behavior from infrastructure. The original single-machine implementation used local threads, JSON files, JSONL inboxes, and in-process dictionaries. Those are useful for teaching and local development, but not sufficient for production.

## Interfaces

Backend contracts live in `runtime/backends/base.py`.

### TaskStore

Owns persistent task board state:

- `create`
- `get`
- `update`
- `list`
- `claim`
- `list_unclaimed`

Production direction: PostgreSQL table with transactions, row-level locks, indexes, audit fields, and explicit ownership transitions.

### MessageStore

Owns mailbox and broadcast behavior:

- `send`
- `drain_inbox`
- `broadcast`

Production direction: Redis Streams, Kafka, NATS, or a PostgreSQL outbox pattern with durable delivery, acknowledgement, retry, and dead-letter support.

### JobQueue

Owns background job execution:

- `enqueue_shell`
- `check`
- `drain_notifications`

Production direction: Celery, RQ, Dramatiq, Temporal, or cloud queue workers with retry, timeout, isolation, observability, and result storage.

### AgentRunner

Owns teammate lifecycle and execution carrier:

- `team_name`
- `upsert_member`
- `get_member`
- `set_member_status`
- `list_members`
- `member_names`
- `start_teammate`

Production direction: Kubernetes Jobs, worker Deployments, remote execution services, or sandboxed containers.

### ReviewStore

Owns human-review state:

- `create_shutdown_request`
- `get_plan_request`
- `set_plan_status`
- `create_review`
- `get_review`
- `list_reviews`
- `approve_review`
- `apply_review`
- `reject_review`

Production direction: PostgreSQL or Redis with TTL, idempotent updates, actor attribution, and audit trail.

## LocalBackend

`runtime/backends/local.py` provides the default implementation:

- `LocalTaskStore`: `.tasks/task_*.json`
- `LocalMessageStore`: `.team/inbox/*.jsonl`
- `LocalJobQueue`: daemon threads and in-process job dictionary
- `LocalAgentRunner`: daemon threads and `.team/config.json`
- `LocalReviewStore`: in-process dictionaries for legacy plan/shutdown state plus `.reviews/REV-*.json`, `.reviews/patches/*.diff`, and `.reviews/apply_audit.jsonl` for human review items, patch previews, and guarded apply events

LocalBackend preserves existing behavior for development and demos.

## Why Local Infrastructure Is Not Production-Grade

- Local threads disappear when the process exits.
- In-process dictionaries do not survive restart or multi-replica deployment.
- JSON/JSONL files have weak concurrency guarantees.
- Local mailboxes do not provide acknowledgement, retry, replay, or dead-letter semantics.
- Background jobs lack resource isolation, scheduling guarantees, and observability.

## Change Rules

- Any backend interface change must update this document and `docs/CHANGELOG.md`.
- Any LocalBackend behavior change must include validation that `python .\harness\agent_harness.py` still starts.
- Manager code should not import `threading`, `subprocess`, or direct task/message file paths for runtime infrastructure.
