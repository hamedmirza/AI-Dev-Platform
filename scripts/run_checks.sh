#!/usr/bin/env bash
ruff check . && mypy app && pytest
