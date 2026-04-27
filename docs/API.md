# API

Implemented endpoints:

- `POST /api/tasks`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/history`
- `GET /api/runs/{run_id}/state-snapshots`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/diff`
- `GET /api/runs/{run_id}/workspace/files`
- `GET /api/runs/{run_id}/workspace/file`
- `POST /api/runs/{run_id}/workspace/file`
- `GET /api/health`
- `GET /api/health/provider`
- `GET /api/config`

Notes:

- authenticated API responses include `X-Request-ID`
- `POST /api/tasks` accepts spec-style optional fields:
  `workspace_path`, `task_type`, `constraints`, `target_files`, `provider`, `model`
- `GET /api/runs/{run_id}` returns persisted task metadata plus the latest workflow state snapshot
- coder outputs may include `file_changes`; those changes are applied only inside the run workspace
- tester commands are parsed and executed only when accepted by the validation command whitelist
