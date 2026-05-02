# ---- Frontend (Vite → app/ui/static) ----
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Python runtime ----
FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
  && apt-get install -y --no-install-recommends gosu \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 1000 --user-group appuser

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY docs ./docs
COPY prompts ./prompts
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
COPY .env.example ./.env.example

# Built operator console assets (overwrites any tracked stubs under app/ui/static)
COPY --from=frontend-build /src/app/ui/static ./app/ui/static

RUN pip install --no-cache-dir . \
  && chmod +x /docker-entrypoint.sh \
  && chown -R appuser:appuser /app

EXPOSE 8400

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8400/api/health/live')"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8400", "--proxy-headers"]
