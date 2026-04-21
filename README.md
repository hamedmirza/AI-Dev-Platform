# AI Dev Platform

This repo is now a working local-first software delivery platform with:

- FastAPI
- server-rendered operator UI
- background run orchestration
- Pydantic v2
- SQLite
- LM Studio via OpenAI-compatible API
- pytest / ruff / mypy

## Local Run
1. Create `.env` from `.env.example` if needed.
2. Start the app:
   - `bash scripts/dev_start.sh`
3. Open:
   - `http://127.0.0.1:8400/ui/login`
4. Log in with the operator token from `.env`.

## Current Features
- operator dashboard, repository view, provider view, settings view, backups view
- task submission and background run processing
- run timeline, artifacts, code-review summary, and workspace diff view
- local backup creation and restore rehearsal
- local repository workspace cloning and cleanup

## Validation
- `ruff check app tests`
- `mypy app`
- `pytest -q`

## Deployment
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## Docs
- [docs/MASTER_BUILD_SPEC.md](docs/MASTER_BUILD_SPEC.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
