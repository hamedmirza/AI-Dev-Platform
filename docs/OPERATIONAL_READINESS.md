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

## Production-safety boot guard

The application calls `Settings.validate_production_safety()` during FastAPI lifespan startup. With `APP_ENV=production`, it raises `ConfigurationError` and refuses to boot when any of the following insecure defaults are still in place:

- `APP_API_TOKEN=dev-token`
- `APP_ENCRYPTION_KEY=change-me`

In development and staging (`APP_ENV != production`) those defaults still work for convenience. Coverage: `tests/unit/test_settings_safety.py::test_validate_production_safety_*`.

`SAFE_MODE` is now in `EDITABLE_ENV_KEYS`, so operators can toggle auto-enqueue on/off from the settings UI without editing `.env` by hand.

## Manual smoke gates

The following gates are **not** in the automated CI matrix and must be re-run manually by an operator before each release. Last execution dates are tracked at the bottom of this section.

### Gate M1 — Multi-repo end-to-end smoke against a real LM Studio

Why deferred: it depends on a live local LM Studio instance and two physical repositories on disk, neither of which is appropriate to seed in CI.

Acceptance criteria:

1. LM Studio is reachable at `LMSTUDIO_BASE_URL` and serves the configured `LMSTUDIO_MODEL`.
2. `SAFE_MODE=false` for the duration of the test.
3. Repository A — this repo (`AI-Dev-Platform`): create a task such as “Add a docstring line to `README.md`”. The run must reach `awaiting_approval`, the operator approves, and the run becomes `completed` with a non-empty diff.
4. Repository B — a second distinct local repo with a `.git` directory (set via `SOURCE_REPO_PATH` for that task or via `source_repo` in the API payload): create a task that touches one file. The run must reach `awaiting_approval`, the operator approves, and the run becomes `completed`.
5. `/api/health/provider` reports `healthy` throughout. No `provider_unavailable` events in either run’s history.
6. No worker thread errors logged at WARNING or higher.

### Gate M2 — Sustained multi-worker stress (beyond the focused unit test)

Why deferred: the bundled unit test exercises the claim guard race directly with two synthetic workers. A sustained, realistic load test against the real orchestration loop requires a long-running fake-provider scenario and is not yet automated.

Acceptance criteria:

1. `WORKER_COUNT >= 3`, fake provider, run at least 50 sequential tasks back-to-back through `/api/tasks`.
2. Inspect the database: no run has more than one `worker_picked_up` event; no run ends in an inconsistent state where `status=running` while no worker is alive.
3. No duplicate `code_patch_applied` events on the same run.

Until M1 and M2 are re-run for the release and recorded below, the release is considered “automated-gate green / manual-gate pending.”

### Last execution log

| Gate | Date (UTC) | Result | Evidence |
|---|---|---|---|
| M1 | 2026-05-18 | PASSED | Two repos, real LM Studio `qwen/qwen3-coder-next`, 55 s + 40 s per run, both approved → completed, zero WARNING+ in server.log. Three real defects surfaced and fixed in commit `0039f74` (LM Studio response_format negotiation, docs validation profile, agent-schema advisory-field defaults). |
| M2 | 2026-05-18 | PASSED | 50 sequential `POST /api/tasks` against `WORKER_COUNT=3` with `FakeProvider`. Drain time 13.6 s. DB audit: 50 distinct runs / 50 `run_started` events (perfect 1:1 — claim-guard atomicity proven), 0 orphans, 0 duplicate `code_patch_applied`. Every pipeline event (`planner_*`, `architect_*`, `ui_designer_*`, `coder_*`, `reviewer_*`, `tester_*`, `code_patch_applied`) appeared exactly 50 times. Zero WARNING+ in server.log. |
