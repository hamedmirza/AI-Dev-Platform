# Operational readiness checklist

Use this before declaring the platform ready for heavy operator use after major changes (clone sources, workers, models, DB schema, UI).

## Isolated validation (recommended)

1. Copy the repository to a temporary directory.
2. Point `APP_SETTINGS_FILE` at a dedicated `.env` for the copy; use a separate `DB_URL`, `WORKSPACE_ROOT`, and `BACKUP_ROOT`.
3. Run the app on an alternate port (for example `8410`) so the live `8400` instance and database are not touched.
4. Install frontend dependencies: `npm --prefix frontend install`.
5. Run backend gates: `ruff check .`, `mypy app`, `pytest`.
6. Run frontend gates: `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`.

## Smoke scenarios

- Health: `/api/health`, `/api/health/provider`, `/api/health/repository`.
- Auth: protected API with `x-api-token` or operator cookie; `/ui/login`.
- Task lifecycle: create a task, confirm a run progresses through stages and produces events and artifacts.
- **Per-task `source_repo`:** local path with `.git`; remote URL only when `ALLOWED_GIT_HOSTS` includes the host.
- **Workers:** `WORKER_COUNT` greater than one should allow overlapping run processing; watch logs for cross-run isolation.
- **Models:** `/api/config/lmstudio/models` returns when LM Studio is running; per-stage env keys resolve in runs.

## GitHub

If no GitHub token is configured, health should report that truthfully. Missing GitHub is not a local readiness failure unless your workflow requires remote PR automation.
