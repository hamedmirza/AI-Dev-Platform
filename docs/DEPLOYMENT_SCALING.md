# Deployment scaling and worker model

## Single-process orchestration (current)

Run dispatch uses an **in-memory queue** (`queue.Queue`) inside the API process, with a **single daemon thread** consuming it (`OrchestrationService` in `app/services/orchestration_service.py`). `enqueue_run` is invoked from HTTP handlers when tasks are created or runs are retried.

**Implications:**

1. **Do not** run multiple Uvicorn/Gunicorn worker processes against the same logical app instance (for example `uvicorn --workers 2` or Gunicorn with `workers > 1` in one container). Each worker would get its own queue; a run enqueued on worker A would never be processed on worker B.

2. **Horizontal scaling** (multiple replicas behind a load balancer) is unsafe unless **all** enqueue and queue consumption happen on the same instance, which generic HTTP load balancers do not guarantee.

3. **Safe baseline:** one container (or one process) per deployment unit, **exactly one** ASGI worker, until the dispatcher is redesigned.

## Planned direction (follow-up work)

- **DB-backed polling:** a worker loop claims `pending` / `queued` runs from SQLite (or another store) with row-level locking or `SKIP LOCKED`, so API processes stay stateless.

- **Or external queue:** Redis / RQ / Celery with a dedicated worker service; API only enqueues job IDs.

Until one of these is implemented, treat this platform as **single-node** for orchestration correctness.
