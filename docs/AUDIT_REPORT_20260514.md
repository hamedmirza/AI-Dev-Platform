# AI-Dev-Platform Audit Report (2026-05-14)

## Scope

Full-pass audit and remediation across backend logic/reliability/security, frontend UX/human-interaction blockers, and CI/verification alignment.

## Confirmed Fixed Issues

### Backend hardening

- Redacted LM Studio secret exposure from config payload:
  - `app/api/routes/config.py`
  - `runtime.lmstudio_api_key` -> `runtime.lmstudio_api_key_configured` (boolean)
- Added planner guard visibility in runtime config:
  - `planner_stage_timeout_seconds`
  - `planner_stage_max_retries`
- Protected sensitive health endpoints with auth:
  - `GET /api/health/ready`
  - `GET /api/health/provider`
  - `GET /api/health/repository`
  - `GET /api/health/github`
- Hardened token comparison using constant-time checks:
  - `app/api/routes/config.py` (`compare_digest`)
- Added secure cookie behavior for operator session under HTTPS/production:
  - `app/ui/routes.py`
- Improved LM Studio 400 diagnostics and model validation:
  - `app/providers/lmstudio.py`
- Reduced provider lifecycle churn by reusing base LMStudio provider instance:
  - `app/providers/registry.py`
- Improved SQLite backup consistency:
  - `app/services/backup_service.py` now uses sqlite online backup API.

### Cancellation checkpoints in long execution paths

- Enabled operator cancellation while running:
  - `app/services/run_service.py`
- Added explicit run cancellation checkpoints in orchestration:
  - `app/services/orchestration_service.py`
  - checkpoints before/after long stage transitions and within retry loops
  - emits `run_cancelled_checkpoint` event and snapshot when cancellation is observed

### Frontend UX / redesign

- Added `runs` hash-aware navigation behavior (`/ui#runs`) and scroll targeting:
  - `frontend/src/main.tsx`
- Fixed project source-repo dual input conflict with explicit mode selection:
  - default/saved/custom repo source path behavior
  - `frontend/src/main.tsx`
- Split large frontend logic by extracting task composer component:
  - `frontend/src/components/TaskComposer.tsx`
  - shared HTTP helper extracted to `frontend/src/lib/http.ts`
- Introduced formal tokenized spacing scale:
  - `frontend/src/styles.css` (`--space-1` … `--space-7`)
- Modernized visual hierarchy / SaaS polish:
  - refined surfaces, shadows, gradients, navigation emphasis, and spacing consistency
  - fixed pipeline columns to match stage model count

### Verification and CI alignment

- Added concurrent worker isolation assertions:
  - `tests/unit/test_api.py`
  - `test_worker_count_two_runs_concurrent_isolation`
- Added cancellation-checkpoint behavior test:
  - `tests/unit/test_api.py`
  - `test_running_run_can_be_cancelled_at_checkpoint`
- Added LM Studio detail parsing unit coverage:
  - `tests/unit/test_lmstudio_response_detail.py`
- Updated local verification gate to include frontend checks:
  - `scripts/run_checks.sh` now runs ruff, mypy, pytest, frontend typecheck, frontend build
- Added CI worker-count matrix coverage (`WORKER_COUNT=2`) for concurrent isolation assertion:
  - `.github/workflows/ci.yml` (`concurrency-isolation` job)
- Updated runbook validation instruction to point to unified gate:
  - `docs/RUNBOOK.md`

## Remaining Known Risks

- Mid-stage cancellation is cooperative (checkpoint-based) and cannot preempt a currently blocking provider HTTP call until timeout/return.
- Multi-worker concurrency has focused assertion coverage, but not sustained soak/load-test characterization.
- Frontend remains largely centralized in `main.tsx`; `TaskComposer` is split out, but further modularization is still recommended.

## Before/After UX Summary

- **Before:** operator workflows had routing ambiguity (`#runs`), conflicting source-repo controls, and low-consistency spacing/theming.
- **After:** improved route-state clarity, cleaner repo selection interactions, a reusable TaskComposer module, tokenized spacing foundation, and stronger SaaS visual hierarchy.

## Recommended Next Roadmap Items

1. Expand frontend decomposition (`RunsBoard`, `RunDetail`, `ProjectsView`, `SettingsView`) into dedicated component modules.
2. Add cancellation-safe provider budget layering (stage timeout + provider timeout alignment with clear operator messaging).
3. Add nightly multi-worker stress suite (N runs, varied repo sizes, cancellation during each stage).
4. Add explicit accessibility audit pass (keyboard focus order, ARIA labeling, live-region announcements).

## Verification Snapshot

- Local full gate:
  - `bash scripts/run_checks.sh`
  - Result: passing (ruff, mypy, pytest, frontend typecheck, frontend build)
- New tests included in passing run:
  - cancellation checkpoint behavior
  - concurrent worker isolation
  - LM Studio response detail parsing
