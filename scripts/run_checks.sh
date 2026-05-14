#!/usr/bin/env bash
set -euo pipefail

ruff check .
mypy app
pytest
npm --prefix frontend run typecheck
npm --prefix frontend run build
