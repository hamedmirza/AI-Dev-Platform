# AI Dev Platform

This repo is now a working local-first software delivery platform with:

- FastAPI
- server-rendered operator UI
- React/Vite operator console served by FastAPI after build
- background run orchestration
- Pydantic v2
- SQLite
- LM Studio via OpenAI-compatible API
- pytest / ruff / mypy

## Source repository

- **GitHub:** [github.com/hamedmirza/AI-Dev-Platform](https://github.com/hamedmirza/AI-Dev-Platform)
- **Clone:** `git clone https://github.com/hamedmirza/AI-Dev-Platform.git`
- Set `SOURCE_REPO_PATH` in `.env` to the **absolute path** of your local checkout so run workspaces clone from the intended tree (see [Environment Variables](#environment-variables)).

## Architecture Diagram (Text)
```text
User/API/UI
  -> FastAPI routes (tasks, runs, health, config, playbooks, lessons, backups, UI)
    -> Orchestration (queued runs, WORKER_COUNT worker threads, STAGES pipeline)
      -> Provider registry -> LM Studio (per-stage model selection)
      -> Tools (workspace guard, filesystem, git clone per task, diff, command runner)
      -> SQLite persistence (tasks, runs, events, artifacts, lessons, playbooks)
    -> Operator UI (React console + server-rendered settings)
```

## Local Run
1. Create `.env` from `.env.example` if needed.
2. Start the app:
   - `bash scripts/dev_start.sh`
3. Open:
   - `http://127.0.0.1:8400/ui/login`
4. Log in with the operator token from `.env`.

## Environment Variables
Core:
- `APP_ENV` (default: `development`)
- `APP_HOST` (default: `0.0.0.0`)
- `APP_PORT` (default: `8400`)
- `APP_API_TOKEN` (required for API/UI auth)
- `DB_URL` (default: `sqlite:///./app.db`)
- `MODEL_PROVIDER` (default: `lmstudio`)
- `LMSTUDIO_BASE_URL` (default: `http://localhost:1234/v1`)
- `LMSTUDIO_MODEL` (default: `qwen2.5-coder-14b-instruct`)
- `LMSTUDIO_MODEL_PLANNER`, `LMSTUDIO_MODEL_ARCHITECT`, `LMSTUDIO_MODEL_UI_DESIGNER`, `LMSTUDIO_MODEL_CODER`, `LMSTUDIO_MODEL_REVIEWER`, `LMSTUDIO_MODEL_TESTER`, `LMSTUDIO_MODEL_SUPERVISOR` (optional; fall back to `LMSTUDIO_MODEL` when unset)
- `LMSTUDIO_API_KEY` (default: `lm-studio`)
- `PROVIDER_TIMEOUT_SECONDS` (default: `60`)
- `GIT_CLONE_TIMEOUT_SECONDS` (default: `300`) — timeout for `git clone` of remote task repositories
- `SOURCE_REPO_PATH` (absolute path to this repo’s checkout on disk; default clone source when a task has no `source_repo`)
- `ALLOWED_GIT_HOSTS` (comma-separated hostnames; **required** for remote `source_repo` HTTPS/SSH URLs on tasks)
- `ALLOWED_SOURCE_REPO_ROOTS` (optional comma-separated absolute path prefixes constraining **local** task `source_repo` paths)
- `WORKSPACE_ROOT` (default: `./workspace`)
- `BACKUP_ROOT` (default: `./backups`)
- `WORKER_COUNT` (default: `1`) — number of orchestration worker threads draining the run queue
- `USE_SCOUT_STAGE` (default: `false`) — prepend read-only file-tree scout block for every run’s planner (can also enable per task with `use_scout`)
- `PLAYBOOK_SUPERVISOR_ENABLED`, `PLAYBOOK_REQUIRE_HUMAN_CONFIRM`, `PLAYBOOK_SUPERVISOR_SYSTEM_PROMPT_PATH` — supervised playbook pipeline (see `/api/playbooks`)
- `LOG_LEVEL` (default: `INFO`)

### Git credentials for remote `source_repo`

Clones run non-interactively with `GIT_TERMINAL_PROMPT=0`. Configure machine-level git credentials (`~/.netrc`, SSH agent, or deploy keys) for private remotes. Credentials are **not** isolated per app unless you use separate OS users or SSH configs; see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for collaboration hygiene.

## LM Studio Startup
1. Start LM Studio locally and load your coding model.
2. Enable the local server in LM Studio.
3. Ensure endpoint and model match your `.env`:
   - `LMSTUDIO_BASE_URL=http://localhost:1234/v1`
   - `LMSTUDIO_MODEL=<loaded-model-id>`
4. Verify from the app:
   - `GET /api/health/provider` should return `healthy` or `degraded`.

## Current Features
- operator dashboard, repository view, provider view, settings view, backups view
- task submission and background run processing
- run timeline, artifacts, code-review summary, and workspace diff view
- structured AI-generated file changes applied inside isolated run workspaces
- dedicated UI designer agent that creates modern frontend direction before coding
- local validation command execution from the tester stage using the command whitelist
- spec-aligned task payloads with optional workspace path, constraints, target files, provider, and model overrides
- reviewer/test retry loops with blocked-state escalation after configured thresholds
- persisted run state snapshots and richer run/task metadata in API responses
- request ID propagation on HTTP responses and contextual request/run logging
- local backup creation and restore rehearsal
- local repository workspace cloning and cleanup

## Frontend Build
The production UI is a standalone React/Vite bundle served by FastAPI from `/ui`. The **Dockerfile** runs `npm ci` and `npm run build` in a Node stage so images always include fresh static assets.

```bash
npm --prefix frontend install
npm --prefix frontend run typecheck
npm --prefix frontend run build
bash scripts/dev_start.sh
```

## API Usage Examples
Create task:
```bash
curl -X POST "http://127.0.0.1:8400/api/tasks" \
  -H "x-api-token: $APP_API_TOKEN" \
  -H "content-type: application/json" \
  -d '{
    "title":"Add run telemetry",
    "description":"Track per-stage provider latency and expose in run snapshots.",
    "workspace_path":"/path/to/repo",
    "task_type":"feature",
    "constraints":["keep changes scoped"],
    "target_files":["app/services/orchestration_service.py"],
    "provider":"lmstudio",
    "model":"qwen2.5-coder-14b-instruct"
  }'
```

Fetch run summary/history/artifacts/state snapshots:
```bash
curl -H "x-api-token: $APP_API_TOKEN" "http://127.0.0.1:8400/api/runs/<run_id>"
curl -H "x-api-token: $APP_API_TOKEN" "http://127.0.0.1:8400/api/runs/<run_id>/history"
curl -H "x-api-token: $APP_API_TOKEN" "http://127.0.0.1:8400/api/runs/<run_id>/artifacts"
curl -H "x-api-token: $APP_API_TOKEN" "http://127.0.0.1:8400/api/runs/<run_id>/state-snapshots"
```

## Validation
- `ruff check app tests docs`
- `mypy app`
- `pytest -q`

## Deployment
- **Image:** multi-stage `Dockerfile` (Node builds [frontend/](frontend) → `app/ui/static`, then Python install). Non-root runtime via `gosu` in [scripts/docker-entrypoint.sh](scripts/docker-entrypoint.sh); `HEALTHCHECK` uses `/api/health/live`.
- **Dev:** [docker-compose.yml](docker-compose.yml) — bind-mount + `--reload`; overrides entrypoint so your host tree is not `chown`ed.
- **Prod-style:** [docker-compose.prod.yml](docker-compose.prod.yml) — named volume `/data` for SQLite + workspaces, no reload, `restart: unless-stopped`. Set `SOURCE_REPO_PATH` (see compose comments) when using repository-backed runs.
- **CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (ruff, mypy, pytest). **GHCR:** push a `v*` tag to build and publish the image ([`.github/workflows/docker.yml`](.github/workflows/docker.yml)).
- **Runbook / scaling:** [docs/RUNBOOK.md](docs/RUNBOOK.md), [docs/DEPLOYMENT_SCALING.md](docs/DEPLOYMENT_SCALING.md).
- `.env.example`

## Docs
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- [docs/OPERATIONAL_READINESS.md](docs/OPERATIONAL_READINESS.md)
- [docs/MASTER_BUILD_SPEC.md](docs/MASTER_BUILD_SPEC.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
- [docs/DEPLOYMENT_SCALING.md](docs/DEPLOYMENT_SCALING.md)
- [docs/API.md](docs/API.md)
- [docs/SPEC_IMPLEMENTATION_MATRIX.md](docs/SPEC_IMPLEMENTATION_MATRIX.md)

## Limitations
- Orchestration uses a shared in-process queue with `WORKER_COUNT` parallel workers; SQLite serializes writes — prefer Postgres (`DB_URL`) for many concurrent runs with heavy artifact writes. See [docs/DEPLOYMENT_SCALING.md](docs/DEPLOYMENT_SCALING.md).
- Provider adapter surface is LM Studio-first; additional backends are not yet implemented.
- Test coverage is strongest in API-level unit tests; deeper multi-process E2E remains limited.

## Next Steps
1. Add first-class provider adapters beyond LM Studio using the same provider interface.
2. Expand integration/E2E suites to include multi-run concurrency and restart recovery scenarios.
3. Add richer patch formats for partial file edits beyond whole-file upsert/delete operations.
