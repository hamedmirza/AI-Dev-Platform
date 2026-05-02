# Runbook

## Local Startup
- Confirm the configured LM Studio endpoint and model are correct in `.env`.
- Start the app with `bash scripts/dev_start.sh`.
- Open `http://127.0.0.1:8400/ui/login`.
- Authenticate with `APP_API_TOKEN`.

### Provider availability at startup
- The API **starts even when LM Studio is unreachable**; the orchestration worker logs a warning and runs will fail until the provider responds again.
- Use `GET /api/health/provider` or the **provider** field on `GET /api/health/ready` to see current provider status.
- For strict external checks (for example only route traffic when the model is up), combine **readiness** with your own probe of `/api/health/provider`.

## Validation
- `ruff check app tests`
- `mypy app`
- `pytest -q`

## Backup
- Use `/ui/backups` to create a local backup.
- Use restore rehearsal before trusting a backup set.

### Container deployments and SQLite
- Production compose (`docker-compose.prod.yml`) stores the database at `/data/app.db` on a **named volume** (`appdata`). Back up that volume or copy the file while the app is stopped.
- After upgrades, run the usual backup before replacing the container; roll back by restoring the SQLite file and pinned image tag.

## Docker (production-style)

1. Copy `.env.example` to `.env` and set at least `APP_API_TOKEN`, LM Studio variables, and **`SOURCE_REPO_PATH`** if you use run workspaces (must point at a **git checkout** with `.git`; you can mount the host repo read-only — see comments in `docker-compose.prod.yml`).
2. Build the image (includes Vite frontend build inside the Dockerfile):
   - `docker compose -f docker-compose.prod.yml build`
3. Start:
   - `docker compose -f docker-compose.prod.yml up -d`
4. Health:
   - Liveness: `GET /api/health/live` (process only).
   - Readiness: `GET /api/health/ready` (database required; provider status included for operators).

### Development compose
- `docker compose up` (default `docker-compose.yml`) bind-mounts the repo and uses `--reload`; it overrides the image entrypoint so the container does not `chown` your host checkout.

### Reverse proxy / TLS
- Terminate TLS at Nginx, Caddy, Traefik, or a cloud load balancer in front of port **8400**.
- When the proxy sets `X-Forwarded-For` / `X-Forwarded-Proto`, the app is started with **`--proxy-headers`** (already set in the production image `CMD`) so forwarded headers are respected.

### Scaling constraints
- See [docs/DEPLOYMENT_SCALING.md](DEPLOYMENT_SCALING.md): do not use multiple Uvicorn/Gunicorn workers per instance until dispatch is redesigned.

## Local Operator Flow
- Create a run from `/ui`.
- Inspect timeline, artifacts, and workspace diff from `/ui/runs/{run_id}`.
- Review the applied AI patch and local validation command artifact before approval.
- Approve, reject, retry, abort, or clean up the workspace from the run screen.
