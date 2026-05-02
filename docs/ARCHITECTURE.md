# Architecture

```text
Client/UI
   ↓
FastAPI API Layer
   ↓
Orchestration Service (in-process queue + N worker threads, WORKER_COUNT)
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
   ├─ Repo lessons (repo_lessons table → planner user prompt)
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
