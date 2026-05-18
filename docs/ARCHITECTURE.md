# Architecture

```text
Client/UI
   ↓
FastAPI API Layer
   ↓
Orchestration Service (in-process queue + N worker threads, WORKER_COUNT)
   ↓
Atomic pending->running claim (single worker wins the run)
   ↓
Sequential pipeline (STAGES in orchestration_service)
   ├─ Planner Agent
   ├─ Architect Agent
   ├─ UI Designer Agent
   ├─ Coder Agent
   ├─ Reviewer Agent
   └─ Tester Agent
   ↓
Optional overlays
   ├─ Read-only scout preamble (USE_SCOUT_STAGE / per-task use_scout)
   ├─ Repo lessons (repo_lessons table → all pipeline agent prompts; auto-persisted from failures)
   └─ Supervised role playbooks (role_playbooks → system prompt overlay)
   ↓
Tool Wrappers + Provider Adapters
   ├─ Filesystem / Workspace Guard
   ├─ Per-run workspace (clone from SOURCE_REPO_PATH or task source_repo_spec)
   ├─ Validation Runners
   └─ LM Studio Provider (per-stage model resolution)
   ↓
SQLite Persistence (WAL mode; optional Postgres for heavy write concurrency)
```

The `langgraph` package is listed for future graph-based orchestration; the **current** runtime is the imperative `OrchestrationService` pipeline above.

## Run lifecycle invariants

- **Claim guard:** `_process_run` performs an atomic `UPDATE runs SET status='running' WHERE id=? AND status='pending'`. Workers that lose the claim race or pick up non-pending runs bail out cleanly. Duplicate enqueues cannot double-process a run.
- **safe_mode parity:** all task creation surfaces (`POST /api/tasks`, `POST /api/projects/{id}/messages`, `POST /api/projects/{id}/start-build`, legacy `POST /ui/tasks`) skip auto-enqueue when `SAFE_MODE=true` and surface that decision in their response/redirect.
- **Approval guard:** `approve_run` fails with `WorkflowError` when the run workspace directory is missing on disk; operators must retry to recreate it before approval can complete.
- **Reject UX:** `reject_run` leaves the run in `review_required` with an actionable `error_message` instructing the operator to press Retry to start a fresh planner pass.
- **Provider validation:** `POST /api/tasks` maps `ConfigurationError` from unsupported provider names to HTTP 422 instead of 500.
