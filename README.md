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
  -> FastAPI routes (tasks, runs, health, config, backups, UI)
    -> Services (task/run/orchestration/repository/artifacts/settings)
      -> Provider registry -> LM Studio provider (OpenAI-compatible API)
      -> Tools (workspace guard, filesystem, git, diff, command runner)
      -> SQLite persistence (tasks, runs, events, artifacts, state snapshots)
    -> Operator UI (server-rendered pages for run control and inspection)
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
- `LMSTUDIO_API_KEY` (default: `lm-studio`)
- `PROVIDER_TIMEOUT_SECONDS` (default: `60`)
- `SOURCE_REPO_PATH` (absolute path to this repo’s checkout on disk; used when cloning into run workspaces)
- `WORKSPACE_ROOT` (default: `./workspace`)
- `BACKUP_ROOT` (default: `./backups`)
- `LOG_LEVEL` (default: `INFO`)

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
The production UI is a standalone React/Vite bundle served by FastAPI from `/ui`.

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
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## Docs
- [docs/MASTER_BUILD_SPEC.md](docs/MASTER_BUILD_SPEC.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
- [docs/API.md](docs/API.md)
- [docs/SPEC_IMPLEMENTATION_MATRIX.md](docs/SPEC_IMPLEMENTATION_MATRIX.md)

## Limitations
- Orchestration currently runs on a single in-process worker queue.
- Provider adapter surface is LM Studio-first; additional backends are not yet implemented.
- Test coverage is strongest in API-level unit tests; deeper multi-process E2E remains limited.

## Next Steps
1. Add first-class provider adapters beyond LM Studio using the same provider interface.
2. Expand integration/E2E suites to include multi-run concurrency and restart recovery scenarios.
3. Add richer patch formats for partial file edits beyond whole-file upsert/delete operations.
