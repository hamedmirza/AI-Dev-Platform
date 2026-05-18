# Full New-App Build Capability Plan

## Goal

Make the platform capable of taking initial product requirements for a new app, asking the right follow-up questions, turning the answers into a scoped build plan, spinning off specialized agents, validating work with the right commands, and keeping a human operator in control through an interactive project chat.

This plan does not assume the current single task pipeline is enough. The current system can run controlled implementation tasks, but full app creation requires a project/app layer, requirements clarification, command approval, multi-run orchestration, and stronger validation truth.

## Current State

Implemented foundations:

- FastAPI app with token/cookie auth.
- React/Vite operator console under `/ui`.
- Task/run lifecycle with planner, architect, UI designer, coder, reviewer, tester, and approval stages.
- Per-run workspace cloning from a source repo or task-level `source_repo`.
- LM Studio provider with per-stage model configuration.
- Run events, artifacts, state snapshots, workspace diff, file browser/editor, backup and restore rehearsal.
- Patch guards, route guards, path traversal guards, and tester command whitelist.
- Repo-scoped lessons and supervised role playbook primitives.

Observed blockers for full new-app builds:

- No first-class project/app entity. Runs are isolated records, not part of a persistent project conversation.
- No interactive requirements interview before execution.
- No structured requirement completeness gate.
- No operator command channel for clarifications, priorities, approvals, and scope changes.
- No multi-task build plan that can spawn, order, pause, and resume child runs.
- Tester model output can disagree with real local validation results; local validation must be the hard source of truth.
- Current validation command policy is too narrow for full-stack app builds.
- UI does not yet make blocked run causes human-friendly enough.
- GitHub PR/remote automation remains unavailable until a token is configured.

## Product Invariant

The app must not blindly build from vague requirements. It should accept a rough idea, then run an interactive intake until it has enough information to create a safe project plan.

Minimum invariant:

- No implementation run starts until project scope, target stack, persistence, auth, validation profile, deployment target, and destructive-action boundaries are explicit or intentionally defaulted by the human.
- Every model-proposed command, external dependency, repo target, and destructive operation is either policy-allowed or human-approved.
- Local validation results override tester claims.

## Target UX

### Project Home

Each app/project gets its own workspace in the console:

- Project name and status.
- Requirement completeness score.
- Conversation thread.
- Current build plan.
- Active agents and child runs.
- Kanban lanes for epics/tasks.
- Validation profile and latest gate results.
- Decisions, assumptions, risks, and human approvals.
- Generated docs and artifacts.

### Interactive Chat

The user can type natural language:

- "Build me a SaaS CRM for small clinics."
- "Use FastAPI and React."
- "Add patient import later."
- "Pause backend agents."
- "Only touch frontend for now."
- "Run tests."
- "Reject this UI direction."
- "Approve task AC-102."

The chat agent must classify every message as one of:

- Requirement.
- Answer to open question.
- Command.
- Scope change.
- Approval/rejection.
- Constraint.
- Bug report.
- Status request.

### Clarification Flow

The app asks targeted questions before planning:

- App purpose and users.
- Must-have workflows.
- Data entities and ownership.
- Authentication and roles.
- UI surfaces.
- Integrations.
- Storage and deployment.
- Validation expectations.
- Non-goals.
- Deadline/priority.

The system should ask only high-value questions. It should not force a long form when the project is simple.

## Data Model

Add project-level tables. Names are conceptual; keep migrations additive.

### `projects`

Fields:

- `id`
- `name`
- `slug`
- `source_repo_spec`
- `repo_key`
- `status`: `intake`, `planning`, `ready_for_approval`, `building`, `blocked`, `awaiting_approval`, `completed`, `cancelled`
- `app_type`
- `target_stack_json`
- `validation_profile_id`
- `created_at`
- `updated_at`

### `project_messages`

Fields:

- `id`
- `project_id`
- `role`: `user`, `assistant`, `system`, `agent`
- `message_type`: `requirement`, `question`, `answer`, `command`, `decision`, `status`, `artifact`
- `content`
- `structured_json`
- `created_at`

### `project_questions`

Fields:

- `id`
- `project_id`
- `question`
- `reason`
- `answer_type`
- `options_json`
- `status`: `open`, `answered`, `skipped`, `defaulted`
- `answer`
- `created_at`
- `answered_at`

### `project_decisions`

Fields:

- `id`
- `project_id`
- `decision_type`
- `summary`
- `value_json`
- `source_message_id`
- `created_at`

### `project_build_items`

Fields:

- `id`
- `project_id`
- `parent_id`
- `title`
- `description`
- `item_type`: `epic`, `task`, `bug`, `validation`, `release`
- `status`: `draft`, `approved`, `queued`, `running`, `blocked`, `awaiting_approval`, `completed`, `cancelled`
- `target_files_json`
- `depends_on_json`
- `assigned_role`
- `run_id`
- `created_at`
- `updated_at`

### `project_agent_sessions`

Fields:

- `id`
- `project_id`
- `role`
- `status`
- `current_run_id`
- `scope_json`
- `last_heartbeat_at`
- `created_at`

### `validation_profiles`

Fields:

- `id`
- `project_id`
- `name`
- `allowed_commands_json`
- `required_commands_json`
- `build_commands_json`
- `runtime_smoke_json`
- `created_at`

## API Plan

### Project APIs

- `POST /api/projects`
  - Creates a project from initial requirements.
  - Does not start implementation automatically unless `auto_start_intake=true`.

- `GET /api/projects`
  - Lists active projects.

- `GET /api/projects/{project_id}`
  - Returns project summary, current status, requirements, decisions, build items, active agents, and latest validation.

- `POST /api/projects/{project_id}/messages`
  - Adds user chat message.
  - Routes message through command/requirement classifier.

- `GET /api/projects/{project_id}/messages`
  - Returns conversation timeline.

- `GET /api/projects/{project_id}/questions`
  - Returns open and answered questions.

- `POST /api/projects/{project_id}/questions/{question_id}/answer`
  - Records answer and re-evaluates readiness.

### Planning APIs

- `POST /api/projects/{project_id}/intake/analyze`
  - Runs requirements analyst.

- `POST /api/projects/{project_id}/plan`
  - Creates full build plan after intake is sufficient.

- `POST /api/projects/{project_id}/plan/approve`
  - Human approves plan and creates build items.

- `POST /api/projects/{project_id}/plan/revise`
  - Human requests changes before agents start.

### Agent APIs

- `POST /api/projects/{project_id}/agents/spawn`
  - Spawns scoped agent session or child run.

- `POST /api/projects/{project_id}/build-items/{item_id}/start`
  - Starts a specific task.

- `POST /api/projects/{project_id}/build-items/{item_id}/pause`
  - Pauses queued/runnable work.

- `POST /api/projects/{project_id}/build-items/{item_id}/retry`
  - Retries a failed/blocked item with new instructions.

- `POST /api/projects/{project_id}/build-items/{item_id}/approve`
  - Approves item output.

- `POST /api/projects/{project_id}/build-items/{item_id}/reject`
  - Rejects item output and captures feedback.

### Command APIs

- `POST /api/projects/{project_id}/commands/preview`
  - Classifies and validates a user command before execution.

- `POST /api/projects/{project_id}/commands/execute`
  - Executes allowed project command or queues approval if risky.

Commands should include:

- Start planning.
- Start selected tasks.
- Pause/resume agents.
- Run validation.
- Change priority.
- Add requirement.
- Lock files.
- Approve/reject.
- Create backup.
- Run restore rehearsal.

## Agent Roles

### Conversation Manager

Owns project chat. It does not write code.

Responsibilities:

- Classify user messages.
- Maintain open questions.
- Summarize current project state.
- Convert commands into structured actions.
- Refuse unsafe or ambiguous commands until clarified.

### Requirements Analyst

Responsibilities:

- Extract requirements from chat.
- Identify missing information.
- Ask minimal, high-value questions.
- Produce requirement spec.
- Maintain assumption log.

Output schema:

- `summary`
- `confirmed_requirements`
- `open_questions`
- `assumptions`
- `non_goals`
- `readiness_score`
- `ready_to_plan`

### Product Architect

Responsibilities:

- Convert requirements into app architecture.
- Define modules, data model, routes, screens, and integrations.
- Identify build slices.

### Delivery Planner

Responsibilities:

- Turn architecture into epics/tasks.
- Set dependencies.
- Decide which tasks can run in parallel.
- Assign roles.
- Define validation profile.

### UI Designer

Responsibilities:

- Produce screen-by-screen UI design.
- Define layout, controls, states, responsive behavior.
- Generate implementation-safe UI acceptance criteria.

### Backend Coder

Owns backend files only.

### Frontend Coder

Owns frontend files only.

### Integration Coder

Owns cross-cutting integration only when explicitly assigned.

### Reviewer

Reviews diffs and scope adherence.

### Tester

Must not invent validation success. It proposes allowed validation commands; the local runner decides pass/fail.

### Release Manager

Aggregates final readiness:

- All required commands passed.
- Runtime smoke passed.
- No active blockers.
- Human approval complete.
- Deployment target clear.

## Agent Spawning Model

Do not let agents recursively spawn arbitrary agents.

Recommended control model:

1. Conversation Manager receives human command.
2. Delivery Planner proposes child tasks and dependencies.
3. Human approves plan or selected tasks.
4. Orchestrator creates child runs with strict ownership:
   - file allowlist
   - role
   - validation profile
   - dependencies
   - blast radius
5. Child runs execute.
6. Parent project aggregates status.

Parallelism rules:

- Parallel tasks must have disjoint write scopes.
- Shared files require a single owner.
- Migrations and route registration are serialized.
- UI and backend can run in parallel only after contracts are approved.
- Final integration is serialized.

## Requirements Readiness Gate

Before implementation, require:

- App name.
- Target users.
- Core workflows.
- Data entities.
- Auth/roles decision.
- Target stack.
- Storage choice.
- UI surfaces.
- Integrations.
- Validation commands.
- Deployment target.
- Source repo target.
- Approval boundary.

The system can default simple items, but it must show them:

- "Defaulting to FastAPI + React + SQLite because no stack was specified."
- "Defaulting to local-only deployment on port 8400."
- "No GitHub automation because token is missing."

## Validation Profiles

The current global tester whitelist is too narrow for full app builds. Replace it with project validation profiles.

### Base Python Profile

Allowed:

- `ruff check .`
- `mypy app`
- `pytest`

### React/Vite Profile

Allowed:

- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build`

### Full-Stack Profile

Allowed:

- Base Python profile.
- React/Vite profile.
- Controlled runtime smoke commands implemented as internal tools, not raw shell:
  - health check
  - login page check
  - authenticated API check
  - browser smoke screenshot

### New App Profile

Generated per project. Example:

- backend lint/type/tests
- frontend type/build
- migration check
- app startup check on isolated port
- health check
- one happy-path browser smoke
- backup rehearsal if persistence exists

Validation rules:

- Local command results are authoritative.
- If tester says passed but a command fails, the run fails.
- If tester includes failures while local commands pass, the system should classify this as tester-output inconsistency, not implementation failure.
- The UI must show exact failing command, return code, timeout, stdout/stderr excerpt, and responsible task.

## UI Plan

Add a Projects area to the React console.

### Navigation

Add:

- Projects.
- Project Chat.
- Build Plan.
- Agents.
- Validation.

### Project Chat Screen

Must show:

- Conversation.
- Open questions.
- Current assumptions.
- Command preview before execution.
- Buttons for approve/reject/start/pause.
- Inline links to tasks/runs/artifacts.

### Build Plan Screen

Must show:

- Epics/tasks tree.
- Dependencies.
- Assigned agent role.
- File ownership.
- Status.
- Validation profile.
- Approval state.

### Agent Board

Must show:

- Active agents.
- Current task.
- Stage.
- Last event.
- Blocker.
- Scope.
- Actions: pause, retry, inspect, approve, reject.

### Validation Screen

Must show:

- Required checks.
- Last result.
- Failing command.
- Logs.
- Runtime smoke.
- Deployment readiness.

## Human-Friendly Failure Reporting

Replace vague blocked states with structured blocker cards:

- What failed.
- Where it failed.
- Why it matters.
- Exact command/result.
- Affected files.
- Suggested next action.
- Retry eligibility.

Example:

```text
Blocked: local validation failed
Command: mypy app
File: app/models/audit_event.py
Error: ForeignKey is not defined
Suggested action: retry coder with focus on SQLAlchemy imports and workspace model typing.
```

## Implementation Phases

### Phase 1 — Project And Chat Foundation

Deliver:

- Project DB tables.
- Project CRUD API.
- Project message API.
- Conversation Manager schema.
- Requirements Analyst schema.
- React project list and project chat screen.

Acceptance:

- User can create a project from rough requirements.
- App asks follow-up questions.
- Answers persist.
- No implementation starts before plan approval.

### Phase 2 — Requirements Gate And Plan Approval

Deliver:

- Requirement readiness evaluator.
- Question generation.
- Assumption/default logging.
- Plan generation endpoint.
- Human approval/revision flow.

Acceptance:

- Vague project stays in `intake`.
- Complete project can produce build plan.
- Human can revise before agents start.

### Phase 3 — Build Items And Scoped Agent Spawning

Deliver:

- Build item tables.
- Parent project to child run linkage.
- Dependency-aware queue.
- File ownership enforcement.
- Role-specific child task creation.

Acceptance:

- Approved plan creates build items.
- Child runs link back to project.
- Parallel runs only start when scopes do not conflict.

### Phase 4 — Validation Profiles

Deliver:

- Validation profile model.
- Project-specific allowed commands.
- Frontend build/typecheck support.
- Runtime smoke internal tools.
- Tester/local-validation contradiction handling.

Acceptance:

- React projects can run frontend gates.
- Full-stack projects can run backend and frontend gates.
- Local validation result is the source of truth.

### Phase 5 — Human-Friendly Blockers

Deliver:

- Structured blocker schema.
- Blocker cards in UI.
- Run/project blocker aggregation.
- Retry prompt includes exact blocker facts.

Acceptance:

- Operator can see why a project is blocked without reading raw JSON.
- Retry action targets the actual failed command/file.

### Phase 6 — Project-Level Memory And Playbooks

Deliver:

- Project-scoped lessons.
- Project-scoped role playbook overlays.
- Human confirmation for playbook activation.
- Conversation summaries injected into planner/coder safely.

Acceptance:

- Lessons do not leak across projects.
- Playbooks require human confirm.
- Future tasks avoid repeated mistakes.

### Phase 7 — End-To-End New App Campaign

Deliver:

- Isolated new app validation campaign.
- At least 20 project-level scenarios.
- Browser smoke for project chat and build board.

Required scenarios:

- Vague initial idea triggers questions.
- Answered questions update readiness.
- Human approves plan.
- Agents spawn with disjoint scopes.
- Backend task completes.
- Frontend task completes.
- Validation failure becomes blocker card.
- Retry fixes blocker.
- User command pauses agents.
- User command changes priority.
- Final release manager declares readiness only after all gates pass.

## Safety Rules

- No raw model command execution.
- No external repo clone unless source policy allows it.
- No dependency install unless validation profile or human approves it.
- No database destructive action without explicit human confirmation.
- No cross-project memory injection.
- No child agent can expand its own file scope.
- No final readiness if any required validation is missing.

## GitHub Boundary

Local new-app builds can work without GitHub.

GitHub-backed automation requires:

- Token configured.
- Repo permission verified.
- Remote push/PR flow smoke-tested.

Until then, GitHub status should remain explicitly out of scope for local build readiness.

## Definition Of Done

The platform is capable of full new-app builds when:

- A user can create a new project from rough requirements.
- The app asks clarifying questions.
- The user can answer and issue commands in project chat.
- A build plan is generated and human-approved.
- Scoped agents are spawned from the plan.
- Child tasks execute with file ownership and dependency control.
- Backend and frontend validation profiles run as appropriate.
- Failed validations produce human-readable blockers.
- Retries are targeted and evidence-based.
- Final project readiness is declared only after all required gates pass.
- At least one realistic new app reaches approval/completion in an isolated clone without manual file edits outside the app.

