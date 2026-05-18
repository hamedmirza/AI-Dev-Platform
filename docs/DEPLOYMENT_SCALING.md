# Deployment scaling and worker model

## Single-process orchestration (current)

Run dispatch uses an **in-memory queue** (`queue.Queue`) inside the API process, drained by **`WORKER_COUNT` daemon threads** (default 1) in `OrchestrationService` (`app/services/orchestration_service.py`). `enqueue_run` is invoked from HTTP handlers when tasks are created or runs are retried.

Each worker that picks a `run_id` off the queue runs an atomic `UPDATE runs SET status='running' WHERE id=? AND status='pending'` (`_claim_pending_run`). Only one worker can win the claim, so duplicate enqueues or accidental cross-worker races are safe within a single process.

**Implications:**

1. **`WORKER_COUNT > 1` inside one process is safe** for the orchestration claim race, but writes still serialize against SQLite. Heavy concurrency benefits from moving to Postgres.

2. **Do not** run multiple Uvicorn/Gunicorn worker processes against the same logical app instance (for example `uvicorn --workers 2` or Gunicorn with `workers > 1` in one container). Each process gets its own in-memory queue; a run enqueued on process A is never picked up by process B. The DB claim guard prevents corruption but the run still stalls until somebody re-enqueues it.

3. **Horizontal scaling** (multiple replicas behind a load balancer) is unsafe unless **all** enqueue and queue consumption happen on the same instance, which generic HTTP load balancers do not guarantee.

4. **Safe baseline:** one container (or one process) per deployment unit, **exactly one** ASGI worker process, `WORKER_COUNT` tuned to available CPU and provider concurrency. Use SQLite for local/dev and Postgres for shared deployments.

## Planned direction (follow-up work)

- **DB-backed polling for multi-process safety:** workers poll the runs table for `pending` rows directly (using the same atomic claim we already have) instead of an in-memory queue. The atomic claim already exists; the queue is the only single-process artefact left.

- **Or external queue:** Redis / RQ / Celery with a dedicated worker service; API only enqueues job IDs and workers claim from the DB.

Until one of these is implemented, treat this platform as **single-process** for orchestration dispatch, but **multi-threaded** within that process.
