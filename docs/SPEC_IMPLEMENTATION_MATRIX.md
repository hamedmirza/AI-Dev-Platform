# Master Spec Implementation Matrix

Status legend:
- `[x]` implemented
- `[~]` partially implemented
- `[ ]` not implemented

## Core objective
- `[x]` accept software tasks -> `app/api/routes/tasks.py`, `app/ui/routes.py`, `app/schemas/task.py`
- `[x]` generate plans/architecture/code/review/test artifacts -> `app/services/orchestration_service.py`, `app/schemas/plan.py`, `app/schemas/architecture.py`, `app/schemas/code_change.py`, `app/schemas/review.py`, `app/schemas/test_result.py`
- `[x]` generate UI/frontend design direction before coding -> `app/agents/ui_designer.py`, `app/agents/prompts/ui_designer.md`, `app/schemas/ui_design.py`
- `[x]` apply AI-generated code patches in isolated run workspaces -> `app/schemas/code_change.py`, `app/services/orchestration_service.py`, `app/services/repository_service.py`
- `[x]` loop on failures until escalation/completion -> `app/services/orchestration_service.py`
- `[x]` expose API + UI workflow -> `app/api/main.py`, `app/api/routes/*.py`, `app/ui/routes.py`, `app/ui/render.py`
- `[x]` local-first LM Studio support -> `app/providers/lmstudio.py`, `app/providers/registry.py`, `app/providers/health.py`

## Functional requirements
- `[x]` task ingestion contract and validation -> `app/schemas/task.py`, `app/api/routes/tasks.py`, `app/services/task_service.py`
- `[x]` run lifecycle statuses (`pending`,`running`,`blocked`,`review_required`,`failed`,`completed`,`cancelled`) -> `app/core/enums.py`, `app/services/orchestration_service.py`, `app/services/run_service.py`
- `[x]` structured step history per node -> `app/db/models.py` (`RunEventModel`), `app/services/orchestration_service.py`, `app/services/run_service.py`
- `[x]` graph state includes required fields -> `app/graph/state.py`, `app/services/orchestration_service.py` (`_build_workflow_state`, snapshots)
- `[x]` workflow transitions and retry thresholds (3/3/5) -> `app/services/orchestration_service.py`
- `[x]` provider interface methods named as spec (`chat_completion`,`structured_completion`,`health_check`,`list_models`) -> `app/providers/base.py`, `app/providers/lmstudio.py`, `app/services/orchestration_service.py`, `app/providers/health.py`
- `[x]` all agent outputs validated by Pydantic models -> `app/services/orchestration_service.py`, `app/schemas/*.py`
- `[x]` tool safety whitelist for validation commands -> `app/tools/command_runner.py`, `app/tools/test_runner.py`, `app/tools/lint_runner.py`
- `[x]` persistence of tasks/runs/state/artifacts/errors/timestamps -> `app/db/models.py`, `app/services/orchestration_service.py`, `app/services/task_service.py`
- `[x]` minimal UI (submit + status + history + outputs) -> `app/ui/routes.py`, `app/ui/render.py`

## API requirements
- `[x]` `POST /api/tasks` -> `app/api/routes/tasks.py`
- `[x]` `GET /api/runs/{run_id}` -> `app/api/routes/runs.py`
- `[x]` `GET /api/runs/{run_id}/history` -> `app/api/routes/runs.py`
- `[x]` `GET /api/runs/{run_id}/artifacts` -> `app/api/routes/runs.py`
- `[x]` `GET /api/health` -> `app/api/routes/health.py`
- `[x]` `GET /api/health/provider` -> `app/api/routes/health.py`
- `[x]` `GET /api/config` -> `app/api/routes/config.py`
- `[x]` additional state endpoint (`GET /api/runs/{run_id}/state-snapshots`) -> `app/api/routes/runs.py`

## LM Studio integration requirements
- `[x]` base URL/model/api key/timeout config -> `app/core/settings.py`, `app/providers/lmstudio.py`
- `[x]` OpenAI-compatible `/chat/completions` usage -> `app/providers/lmstudio.py`
- `[x]` provider health endpoint -> `app/providers/health.py`, `app/api/routes/health.py`
- `[x]` provider selection via registry/config -> `app/providers/registry.py`, `app/api/routes/tasks.py`, `app/services/orchestration_service.py`
- `[x]` startup health failure when provider unavailable -> `app/services/orchestration_service.py` (`start`)

## Prompting requirements
- `[x]` prompts stored as files -> `app/agents/prompts/*.md`
- `[x]` prompts loaded from files, not hardcoded system prompts -> `app/services/orchestration_service.py`

## Persistence and migrations
- `[x]` SQLite initialization -> `app/db/session.py`
- `[x]` in-place lightweight schema evolution for deployed DBs -> `app/db/session.py` (`_apply_lightweight_migrations`)

## Observability requirements
- `[x]` request IDs -> `app/api/main.py`, `app/core/request_context.py`, `app/core/logging.py`
- `[x]` run IDs in log context -> `app/core/request_context.py`, `app/core/logging.py`, `app/services/orchestration_service.py`
- `[x]` step-level/node start-end logs/events -> `app/services/orchestration_service.py`, `app/db/models.py` (`RunEventModel`)
- `[x]` provider latency logging -> `app/providers/lmstudio.py` (`structured_completion`, `health_check`)
- `[x]` validation command execution logs -> command wrappers return structured results and orchestration stores validation events/artifacts

## Tests requirement coverage
- `[x]` end-to-end run flow tests (API/UI) -> `tests/unit/test_api.py`
- `[x]` retry/block behavior tests -> `tests/unit/test_api.py`
- `[x]` command whitelist + task contract tests -> `tests/unit/test_tools.py`
- `[~]` spec-listed integration/e2e directories are present but deep scenario coverage is still concentrated in unit-style API tests -> `tests/integration`, `tests/e2e`

## Docs requirement coverage
- `[x]` README updated with current features and validation commands -> `README.md`
- `[x]` API doc updated with implemented endpoints and request ID notes -> `docs/API.md`
- `[x]` README items explicitly requested by spec (architecture diagram text, LM Studio startup walkthrough, limitations/next steps sections) -> `README.md`
