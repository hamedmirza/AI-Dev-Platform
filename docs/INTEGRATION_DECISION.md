# Integration Strategy Decision

This document records the locked-in integration strategy for the AI Dev Platform
after the run-reliability audit and the open-source product benchmark.

## Goals Recap

1. Professional IDE features (editor, LSP, git, terminal, multi-root workspace).
2. Multi-agent control with governance (Planner → Architect → UI Designer → Coder → Reviewer → Tester).
3. Multi-repo support (per-task `source_repo_spec`, per-repo lessons and playbooks).
4. Actually works end-to-end: deterministic lifecycle, no run-blocking races, clear operator UX.

## Product Benchmark (Open-Source Options Reviewed)

| Product | Role it owns | Pros | Cons | Replaces backend? |
|---------|--------------|------|------|-------------------|
| **OpenHands** | Autonomous coding agent platform (SDK + cloud + CLI) | Mature multi-agent execution; sandboxed runtime; SWE-bench leader; GitHub/GitLab native integration | Heavy adoption; opinionated runtime; replacing our orchestration is a multi-month rewrite | Yes (but disruptive) |
| **Cline** | IDE-embedded coding agent (VS Code, JetBrains, CLI, SDK, web Kanban) | Excellent IDE UX; human-in-the-loop approval; multi-root workspace; works in Cursor too | Single agent loop; no governed multi-stage pipeline; no run DB or operator approval queue | No |
| **Continue.dev** | PR/CI quality checks defined in `.continue/checks/*.md` | Source-controlled review checks; CI-native; light to adopt | Not an orchestration engine; not a multi-agent pipeline | No |
| **Open WebUI Pipelines** | OpenAI-compatible plugin framework + chat UI | Quick UI; Python plugins; integrates with LM Studio out of the box | Arbitrary plugin code execution risk; no built-in software-delivery governance | No |

## Decision

**Keep this repository as the orchestration core (the system of record). Add an IDE-centric client *after* reliability gates pass.**

### Why
- Our backend already owns the parts no off-the-shelf product gives us:
  multi-stage governed pipeline, retry policies, repo-scoped lessons, PatchGuard,
  scoped validation profiles, run history, approval queue.
- The fastest path to "professional IDE features" is to integrate with an editor
  the user already has (VS Code/Cursor), not to rebuild one.
- The audit-driven reliability fixes already landed make the backend safe to
  expose to a thin client without inheriting hidden race or lifecycle defects.

### Roles of each product, going forward
- **AI Dev Platform (this repo):** orchestration core, multi-repo registry, run lifecycle, operator approval, lessons memory. Source of truth.
- **VS Code / Cursor (later):** IDE shell. Reached via a thin extension that calls the existing FastAPI endpoints. Read-only run monitoring + task submission in v1.
- **Cline (optional, later):** considered only as inspiration for the extension UX; not adopted as core. We may reuse its UX patterns for approval flows.
- **Continue.dev (optional, later):** considered for CI-side enforcement of repo-scoped policies that complement (not replace) our reviewer agent.
- **Open WebUI / OpenHands / Dify:** **not adopted**. Out of scope for this iteration; revisiting is gated on a concrete second product class (e.g. RAG over specs) that does not belong in the dev pipeline.

## Verification Gates (Before Phase 4 IDE Work Begins)

These must all be true before any extension/scaffold work is greenlit:

1. **Full unit + integration suites pass.** 53 unit tests green (was 47 before this iteration; +6 new lifecycle/race tests).
2. **Atomic run claim demonstrated.** `tests/unit/test_lifecycle_and_claim.py::test_claim_pending_run_only_one_worker_wins` and `test_claim_skips_non_pending_runs` enforce this in code; documented in `docs/ARCHITECTURE.md`.
3. **safe_mode parity verified.** `test_safe_mode_ui_task_creation_does_not_auto_enqueue` enforces the legacy UI path behaves like the API path.
4. **Lifecycle UX deterministic.** `test_approve_fails_when_workspace_missing` and `test_reject_leaves_run_idle_with_actionable_message` lock the new operator-facing invariants.
5. **At least two distinct repos complete an end-to-end run cycle** without manual DB intervention. Tracked as a manual smoke-test acceptance criterion before announcing the extension build phase.

## Phase 4 Scope (IDE Client, when allowed to start)

Minimum viable extension:
- Sidebar tree of runs (read-only) backed by `GET /api/runs`.
- "Submit task" command backed by `POST /api/tasks`.
- Run detail webview backed by `GET /api/runs/{id}` and `/history`, `/state-snapshots`, `/artifacts`, `/diff`.
- "Approve / Reject / Retry / Abort" commands backed by the existing run-action endpoints.
- "Open run workspace" → `vscode.workspace.openFolder` on `{WORKSPACE_ROOT}/run-{run_id}`.

Explicitly deferred:
- Live (WebSocket/SSE) streaming. v1 polls.
- Editor-side patch generation. The platform's coder agent remains authoritative for proposing changes.
- Cursor-specific APIs. The extension must work in vanilla VS Code first.

## Why Not Adopt One Of These As Core

- **OpenHands:** strong product but adopting it as core means rewriting our governance layer on top of theirs. Multi-month migration with unclear net win because we'd still own the multi-repo lessons memory, validation profiles, and operator approval. Net effect: more risk, not less.
- **Cline:** brilliant IDE agent UX but it does **not** replace a backend with run history, approval gates, governed retries, and per-repo memory. Using Cline as core means rebuilding our backend on top of a single-agent loop and a per-developer IDE session — wrong direction for a team/governance platform.
- **Continue.dev:** narrowly scoped to PR-time checks. Useful as a CI complement, not as an orchestration replacement.
- **Open WebUI Pipelines:** plugin framework for chat UIs with arbitrary code execution. Wrong governance posture for a system that must run validated, approved software changes on real repos.

## Result

- Backend: hardened (claim guard, safe_mode parity, approval/reject UX, provider error mapping) and now safe to expose to additional clients.
- Strategy: locked. Keep the backend; integrate VS Code/Cursor via a thin extension; do not adopt any of the surveyed products as the core in this iteration.
- Status: all Phase 1–3 todos complete; Phase 4 (IDE client) is gated on the verification list above.
