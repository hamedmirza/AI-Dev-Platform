# Runbook

## Local Startup
- Confirm the configured LM Studio endpoint and model are correct in `.env`.
- Start the app with `bash scripts/dev_start.sh`.
- Open `http://127.0.0.1:8400/ui/login`.
- Authenticate with `APP_API_TOKEN`.

## Validation
- `ruff check app tests`
- `mypy app`
- `pytest -q`

## Backup
- Use `/ui/backups` to create a local backup.
- Use restore rehearsal before trusting a backup set.

## Local Operator Flow
- Create a run from `/ui`.
- Inspect timeline, artifacts, and workspace diff from `/ui/runs/{run_id}`.
- Approve, reject, retry, abort, or clean up the workspace from the run screen.
