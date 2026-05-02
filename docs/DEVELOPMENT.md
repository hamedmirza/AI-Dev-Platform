# Development and multi-agent hygiene

When several people or agents change this repository in parallel:

1. **Sync first:** `git fetch` and merge or rebase onto the integration branch before starting substantive work.
2. **High-churn files:** Expect frequent conflicts in `app/services/orchestration_service.py`, `app/api/main.py`, `app/core/settings.py`, `app/services/settings_service.py`, `app/ui/routes.py`, `frontend/src/main.tsx`, and `app/db/session.py`. Re-read the latest version before editing.
3. **Additive migrations only:** New SQLite columns and tables must be added in a backward-compatible way (`ALTER TABLE ... ADD COLUMN` guarded by column checks, or `create_all` for new tables).
4. **Quality gate before merge:** Run `ruff check app tests`, `mypy app`, and `pytest`. For UI changes, also `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`.
5. **Small, reviewable changes:** Prefer focused commits over large mixed refactors so bisect and review stay tractable.
