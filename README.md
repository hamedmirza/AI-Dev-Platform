# AI Dev Platform — Cursor Ready Bundle

This repo is a starter scaffold for building a local-first multi-agent software development platform using:

- FastAPI
- LangGraph
- Pydantic v2
- SQLite
- LM Studio via OpenAI-compatible API
- pytest / ruff / mypy

## Included
- Full build spec: `docs/MASTER_BUILD_SPEC.md`
- Cursor rules: `.cursor/rules/ai-dev-team.mdc`
- Cursor kickoff prompt: `prompts/cursor_kickoff_prompt.txt`
- Repo scaffold matching the target architecture
- Starter `pyproject.toml`
- `.env.example`
- Minimal placeholder prompt files

## Use in Cursor
1. Open this folder in Cursor.
2. Make sure `.cursor/rules/ai-dev-team.mdc` is enabled.
3. Open `docs/MASTER_BUILD_SPEC.md`.
4. Paste `prompts/cursor_kickoff_prompt.txt` into Cursor chat.
5. Let Cursor implement phase 1 incrementally.

## Notes
This bundle is intentionally scaffold-first. It is meant to reduce ambiguity and give Cursor a controlled starting point rather than pretending the full platform is already implemented.
