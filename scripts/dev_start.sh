#!/usr/bin/env bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8400
