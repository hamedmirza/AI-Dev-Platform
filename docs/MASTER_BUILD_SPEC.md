# AI Multi-Agent Developer Platform — Master Build Spec

## Objective
Build a production-structured local-first multi-agent software development platform that acts like a small software team.

The system must:
- accept a software task
- break it into scoped work
- assign work to specialized agents
- generate implementation plans
- produce code changes
- review code against rules
- run tests and validations
- loop on failures until completion or escalation
- expose the workflow through an API and simple UI
- support local model backends first
- support LM Studio through OpenAI-compatible API
- be structured so cloud models can be added later without refactor

This is not a demo script.
This must be a clean, extensible, testable system.

---

# Non-Negotiable Rules

## Delivery rules
- Do not guess.
- Do not invent missing files, APIs, or dependencies without checking first.
- Do not change unrelated files.
- Do not silently refactor working modules unless required by this spec.
- Do not create duplicate implementations.
- Do not leave TODO placeholders unless explicitly approved by this spec.
- Do not hardcode fake results.
- Do not claim a feature works unless it is implemented and testable.
- Do not skip tests.
- Do not skip logging.
- Do not skip type hints.
- Do not skip structured schemas.
- Do not use mock logic in production paths.

## Change control rules
For each task:
1. inspect relevant files first
2. state the planned file changes
3. implement in small steps
4. run lint/type/tests after each meaningful milestone
5. report exact pass/fail results
6. stop and explain if blocked

## Code quality rules
- Python 3.12
- strong typing everywhere practical
- Pydantic for contracts
- FastAPI for service API
- LangGraph for orchestration
- LangChain components only where useful
- no framework sprawl
- clean modular boundaries
- no giant god files
- functions should be focused and testable
- use structured logging
- all important state transitions must be logged

## Model/provider rules
- local-first
- primary provider: LM Studio using OpenAI-compatible endpoint
- model/provider config must be abstracted
- no provider-specific logic leaked into agent business logic
- support later addition of Ollama or cloud providers via adapter pattern

## Security rules
- never execute arbitrary shell commands from model output directly
- all tool execution must be validated through controlled tool wrappers
- file access must be bounded to workspace/project roots
- secrets must come from environment/config only
- no secrets in prompts, logs, fixtures, or source files

---

# Product Scope

## Core use case
A user submits a development task such as:
- build a feature
- fix a bug
- refactor a module
- write tests
- review a pull request diff
- generate architecture plan

The system then:
1. classifies the task
2. creates a structured plan
3. routes work through specialized agents
4. produces artifacts
5. validates results
6. retries or escalates when necessary

## Initial agent roles
Implement these agents first:

### 1. Planner Agent
Responsibilities:
- interpret user request
- classify task type
- extract constraints
- produce structured implementation plan
- identify required files/modules

Outputs:
- task summary
- assumptions
- risks
- implementation steps
- acceptance criteria

### 2. Architect Agent
Responsibilities:
- map plan to system structure
- define touched modules
- define contracts/interfaces
- identify data flow and dependency changes
- prevent chaotic edits

Outputs:
- file change plan
- module boundaries
- dependency notes
- schema updates
- migration notes if needed

### 3. Coder Agent
Responsibilities:
- implement scoped code changes
- follow architect instructions
- produce minimal diffs
- avoid unrelated edits

Outputs:
- code patch plan
- changed file list
- implementation notes

### 4. Reviewer Agent
Responsibilities:
- inspect code changes
- detect rule violations
- detect overreach
- detect missing tests
- detect unsafe patterns
- send back actionable review items

Outputs:
- review status
- issues list
- severity
- approval or rejection

### 5. Tester Agent
Responsibilities:
- run or prepare validation commands
- interpret failures
- summarize broken areas
- propose retry inputs for coder

Outputs:
- test summary
- failed checks
- probable cause
- recommended fix focus

## Optional later agents
Do not build these until core workflow is stable:
- Documentation Agent
- Refactor Agent
- Security Agent
- PR Agent
- Research Agent
- Dependency Upgrade Agent

---

# Required Architecture

## Stack
- Backend: FastAPI
- Orchestration: LangGraph
- Schemas: Pydantic v2
- HTTP client: httpx
- Logging: standard logging or structlog
- Testing: pytest
- Type checking: mypy
- Linting/formatting: ruff
- UI: simple React frontend or server-rendered minimal interface
- Persistence: SQLite first
- Task queue: in-process first, designed for later Celery/Redis replacement if needed

## System layers

### Layer 1: API
Responsibilities:
- accept tasks
- create runs
- fetch run status
- fetch artifacts
- expose configuration health
- expose provider health

### Layer 2: Orchestration
Responsibilities:
- graph state definition
- node execution
- transitions
- retry logic
- stop conditions
- escalation conditions
- run history

### Layer 3: Agents
Responsibilities:
- prompt composition
- structured output parsing
- role-specific logic
- validation of outputs

### Layer 4: Tools
Responsibilities:
- safe filesystem access
- file reading
- file writing
- diff creation
- test/lint runner
- git status/diff reader
- code search wrappers

### Layer 5: Providers
Responsibilities:
- LM Studio adapter
- generic chat model interface
- health checking
- timeout handling
- retry handling
- model selection

### Layer 6: Persistence
Responsibilities:
- store tasks
- store runs
- store state snapshots
- store artifacts
- store review outcomes
- store validation results

---

# Required File Structure

```text
ai_dev_platform/
  app/
    api/
      main.py
      routes/
        tasks.py
        runs.py
        health.py
        config.py
    core/
      settings.py
      logging.py
      exceptions.py
      enums.py
    graph/
      state.py
      nodes/
        planner_node.py
        architect_node.py
        coder_node.py
        reviewer_node.py
        tester_node.py
      edges.py
      workflow.py
    agents/
      base.py
      planner.py
      architect.py
      coder.py
      reviewer.py
      tester.py
      prompts/
        planner.md
        architect.md
        coder.md
        reviewer.md
        tester.md
    providers/
      base.py
      lmstudio.py
      registry.py
      health.py
    tools/
      base.py
      filesystem.py
      workspace_guard.py
      diff_tools.py
      git_tools.py
      test_runner.py
      lint_runner.py
      search_tools.py
    schemas/
      task.py
      plan.py
      architecture.py
      code_change.py
      review.py
      test_result.py
      run.py
      artifact.py
      provider.py
    services/
      task_service.py
      run_service.py
      artifact_service.py
      orchestration_service.py
    db/
      models.py
      session.py
      migrations/
    ui/
      frontend/
    templates/
  tests/
    unit/
    integration/
    e2e/
  scripts/
    dev_start.sh
    run_checks.sh
    seed_demo_data.py
  docs/
    MASTER_BUILD_SPEC.md
    ARCHITECTURE.md
    API.md
    RUNBOOK.md
  .env.example
  pyproject.toml
  README.md
```

---

# Functional Requirements

## 1. Task ingestion
Create API endpoint to submit task:
- title
- description
- repo/workspace path
- task type optional
- constraints optional
- target files optional
- model/provider override optional

On submit:
- validate payload
- create task record
- create run record
- start workflow

## 2. Run lifecycle
Each run must have statuses:
- pending
- running
- blocked
- review_required
- failed
- completed
- cancelled

Each node execution must append structured step history.

## 3. Graph state
State must include at minimum:
- run_id
- task_id
- title
- description
- workspace_path
- task_type
- constraints
- target_files
- current_step
- planner_output
- architecture_output
- code_output
- review_output
- test_output
- artifacts
- errors
- retry_count
- status

## 4. Workflow logic
Initial workflow:

1. planner
2. architect
3. coder
4. reviewer
5. tester

Transitions:
- if reviewer rejects -> back to coder
- if tester fails -> back to coder
- if retries exceed threshold -> blocked
- if reviewer approves and tests pass -> completed

Retry thresholds:
- reviewer loop max 3
- tester loop max 3
- total workflow retries max 5

## 5. Provider abstraction
Implement provider interface with methods:
- chat_completion
- structured_completion
- health_check
- list_models optional

LM Studio provider must:
- accept base URL
- accept model name
- use OpenAI-compatible API pattern
- support timeout config
- return normalized response objects

## 6. Structured outputs
All agent outputs must map to Pydantic models.
No free-form unvalidated agent response should drive workflow transitions.

## 7. Tool safety
Tool wrappers must enforce:
- workspace-bound file access
- allowed command whitelist for validation steps
- safe subprocess execution
- timeout handling
- stdout/stderr capture
- explicit return codes

Allowed initial validation commands:
- pytest
- ruff check
- ruff format --check
- mypy

Do not allow arbitrary command execution from prompts.

## 8. Persistence
Use SQLite first.
Store:
- tasks
- runs
- node results
- artifacts
- validation results
- timestamps
- error messages

## 9. Minimal UI
Build a minimal UI that can:
- submit a task
- show run status
- show step history
- show generated plan
- show review/test outcomes

Keep UI simple and functional.
Do not over-design first iteration.

---

# Data Contracts

## TaskCreate
```python
class TaskCreate(BaseModel):
    title: str
    description: str
    workspace_path: str
    task_type: str | None = None
    constraints: list[str] = []
    target_files: list[str] = []
    provider: str | None = None
    model: str | None = None
```

## PlannerOutput
```python
class PlannerOutput(BaseModel):
    summary: str
    assumptions: list[str]
    risks: list[str]
    steps: list[str]
    acceptance_criteria: list[str]
    files_of_interest: list[str]
```

## ArchitectOutput
```python
class ArchitectOutput(BaseModel):
    touched_files: list[str]
    new_files: list[str]
    module_changes: list[str]
    interfaces: list[str]
    dependency_changes: list[str]
    notes: list[str]
```

## CoderOutput
```python
class CoderOutput(BaseModel):
    changed_files: list[str]
    implementation_summary: str
    notes: list[str]
```

## ReviewOutput
```python
class ReviewIssue(BaseModel):
    severity: str
    file: str | None = None
    message: str

class ReviewOutput(BaseModel):
    approved: bool
    summary: str
    issues: list[ReviewIssue]
```

## TestOutput
```python
class ValidationCheck(BaseModel):
    name: str
    passed: bool
    return_code: int
    summary: str

class TestOutput(BaseModel):
    all_passed: bool
    checks: list[ValidationCheck]
    failure_summary: str | None = None
```

---

# API Requirements

## Endpoints
Implement at minimum:

### POST /api/tasks
Create task and start run

### GET /api/runs/{run_id}
Get run summary

### GET /api/runs/{run_id}/history
Get run step history

### GET /api/runs/{run_id}/artifacts
Get run artifacts

### GET /api/health
Global health

### GET /api/health/provider
Provider health

### GET /api/config
Safe runtime config summary without secrets

---

# LM Studio Integration Requirements

## Environment variables
```env
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8400

DB_URL=sqlite:///./app.db

MODEL_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen2.5-coder-14b-instruct
LMSTUDIO_API_KEY=lm-studio

WORKSPACE_ROOT=./workspace
LOG_LEVEL=INFO
```

## Provider behavior
- verify LM Studio health at startup
- fail clearly if unreachable
- expose provider health endpoint
- do not embed provider logic in agents
- provider selection must come from config/registry

---

# Prompting Requirements

## General
Prompts must be stored in dedicated files, not hardcoded giant strings in Python.

## Prompt rules
Every prompt must:
- define role
- define boundaries
- require structured output
- forbid guessing
- forbid unrelated changes
- forbid unsafe actions
- require concise reasoning in outputs, not hidden chain of thought

## Example planner prompt expectations
- summarize task
- list assumptions
- list risks
- produce implementation steps
- output valid JSON matching PlannerOutput

---

# Development Plan

## Phase 1 — Foundation
Build:
- project skeleton
- settings/config
- logging
- database layer
- provider abstraction
- LM Studio adapter
- base schemas

Acceptance:
- app starts
- health endpoint works
- provider health works
- DB initializes

## Phase 2 — Core orchestration
Build:
- graph state
- planner node
- architect node
- coder node
- reviewer node
- tester node
- workflow edges
- run persistence

Acceptance:
- workflow runs end-to-end on a sample task
- step history stored
- status updates correctly

## Phase 3 — Tooling and safety
Build:
- workspace guard
- filesystem wrappers
- lint runner
- test runner
- subprocess safety
- artifact storage

Acceptance:
- file access cannot escape workspace root
- validation commands return structured output
- failed validation loops back correctly

## Phase 4 — API and UI
Build:
- tasks route
- runs route
- artifacts route
- minimal UI

Acceptance:
- user can submit task
- monitor run
- view outputs

## Phase 5 — Hardening
Build:
- retry controls
- blocked state
- better error handling
- integration tests
- e2e sample

Acceptance:
- reviewer rejection loop works
- test failure loop works
- blocked state works after threshold

---

# Required Tests

## Unit tests
- settings load
- provider registry
- LM Studio adapter normalization
- schema validation
- workspace path guard
- tool wrapper return objects
- node state transitions

## Integration tests
- submit task -> workflow starts
- planner -> architect -> coder path
- reviewer reject -> coder retry
- tester fail -> coder retry
- provider unavailable -> graceful failure

## E2E tests
- complete a simple task from API submission to completion
- retrieve run history and artifacts

---

# Observability

Implement:
- request IDs
- run IDs
- step-level logs
- node start/end logs
- provider latency logging
- validation command logs
- failure reason logging

Do not log:
- secrets
- raw credentials
- full environment dumps

---

# Definition of Done

A feature is done only if:
- code exists
- endpoint or UI path exists if relevant
- schemas are validated
- tests exist
- lint/type/tests pass
- logs are meaningful
- no fake placeholders remain
- README/docs updated

---

# README Requirements
README must include:
- project purpose
- architecture diagram in text
- setup instructions
- environment variables
- LM Studio startup instructions
- API usage examples
- test commands
- limitations
- next steps

---

# Initial Build Task for Cursor

Execute in this order:

1. inspect repository and confirm whether this is a greenfield build or retrofit
2. create the file/folder structure from this spec
3. create pyproject.toml with required dependencies and dev tools
4. implement settings, logging, and config
5. implement provider abstraction and LM Studio provider
6. implement health endpoints
7. implement database initialization
8. implement schemas
9. implement graph state and empty node contracts
10. implement basic workflow and sample stub execution using real provider calls where possible
11. implement safe test/lint runners
12. implement task/run endpoints
13. implement minimal UI
14. add tests
15. run all checks and report exact results

---

# Output Format Cursor Must Follow

For every major step, output:

## Step
Name of step

## Files to create/update
- list files

## Reason
Short justification

## Validation
Commands run and exact result

## Risks
Anything uncertain or blocked

Do not skip this reporting format.

---

# Strict Instruction to Cursor
Follow this document exactly.
Do not compress phases into one giant uncontrolled edit.
Do not rewrite the whole codebase unless inspection proves that is necessary.
Prefer incremental, testable progress.
If a conflict appears between this spec and the current repository structure, inspect first and preserve working patterns where possible while still satisfying the architecture goals.
