
from __future__ import annotations

import ast
import json
import logging
import queue
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.core.enums import ArtifactType, ProviderStatus, RunStage, RunStatus, StringEnum
from app.core.exceptions import ConfigurationError, ProviderError, WorkflowError
from app.core.request_context import set_request_id, set_run_id
from app.core.settings import get_settings
from app.db.models import ArtifactModel, RunEventModel, RunModel, RunStateSnapshotModel, TaskModel
from app.db.session import get_session_factory
from app.graph.state import WorkflowState
from app.providers.registry import get_provider, resolve_provider
from app.providers.stage_models import effective_lmstudio_model_for_stage
from app.schemas.architecture import ArchitectureResponse
from app.schemas.code_change import CodeChangeResponse, FileChange, LineChange
from app.schemas.plan import PlanResponse
from app.schemas.review import ReviewResponse
from app.schemas.test_result import TestResultResponse
from app.schemas.ui_design import UIDesignResponse
from app.services.lesson_service import load_lessons_prompt_prefix
from app.services.playbook_service import load_active_playbook_overlay
from app.services.repository_service import (
    create_run_workspace,
    delete_run_workspace_file,
    get_run_workspace_diff,
    get_run_workspace_path,
    list_run_workspace_files,
    write_run_workspace_file,
)
from app.services.source_repo_policy import repo_key_for_source_spec, validate_source_repo_spec
from app.tools.base import CommandResult
from app.tools.command_runner import run_validation_command

logger = logging.getLogger(__name__)

MAX_REVIEW_RETRIES = 3
MAX_TEST_RETRIES = 3
MAX_TOTAL_RETRIES = 5


@dataclass(frozen=True)
class StageDefinition:
    stage: RunStage
    artifact_type: ArtifactType
    artifact_title: str
    schema: type[BaseModel]
    system_prompt_path: str
    user_prompt_template: str


class StageTimeoutError(TimeoutError):
    pass


class PatchGuardError(ValueError):
    pass


STAGES: list[StageDefinition] = [
    StageDefinition(
        stage=RunStage.PLANNER,
        artifact_type=ArtifactType.PLAN,
        artifact_title="Implementation plan",
        schema=PlanResponse,
        system_prompt_path="app/agents/prompts/planner.md",
        user_prompt_template=(
            "Return JSON with summary, assumptions, risks, steps, and acceptance_criteria "
            "for this software task:\n\n{request_text}"
        ),
    ),
    StageDefinition(
        stage=RunStage.ARCHITECT,
        artifact_type=ArtifactType.ARCHITECTURE,
        artifact_title="Architecture change plan",
        schema=ArchitectureResponse,
        system_prompt_path="app/agents/prompts/architect.md",
        user_prompt_template=(
            "Given this task, return JSON with touched_modules, file_change_plan, "
            "dependency_notes, and migration_notes:\n\n{request_text}"
        ),
    ),
    StageDefinition(
        stage=RunStage.UI_DESIGNER,
        artifact_type=ArtifactType.UI_DESIGN,
        artifact_title="UI design direction",
        schema=UIDesignResponse,
        system_prompt_path="app/agents/prompts/ui_designer.md",
        user_prompt_template=(
            "Return JSON with design_summary, visual_system, layout_plan, interaction_notes, "
            "accessibility_notes, and implementation_notes for this task. Make the UI modern, "
            "polished, and cool while preserving operational usability:\n\n{request_text}"
        ),
    ),
    StageDefinition(
        stage=RunStage.CODER,
        artifact_type=ArtifactType.CODE_CHANGE,
        artifact_title="Proposed code change",
        schema=CodeChangeResponse,
        system_prompt_path="app/agents/prompts/coder.md",
        user_prompt_template=(
            "Return JSON with changed_files, implementation_notes, requires_operator_approval, "
            "line_changes, and file_changes for this task. Prefer line_changes for small "
            "line-level edits. line_changes objects must contain path, operation, anchor, "
            "content, and optional occurrence. Use file_changes only for whole-file upsert/delete "
            "edits that are truly necessary. Preserve existing "
            "FastAPI APIRouter route paths, function names, imports, auth/session behavior, "
            "redirects, and UI flows unless explicitly requested otherwise. Do not replace "
            "app/ui/routes.py with a standalone FastAPI app:\n\n{request_text}"
        ),
    ),
    StageDefinition(
        stage=RunStage.REVIEWER,
        artifact_type=ArtifactType.REVIEW,
        artifact_title="Review result",
        schema=ReviewResponse,
        system_prompt_path="app/agents/prompts/reviewer.md",
        user_prompt_template=(
            "Review the proposed work for this task. Return JSON with approved, summary, "
            "and issues:\n\n{request_text}"
        ),
    ),
    StageDefinition(
        stage=RunStage.TESTER,
        artifact_type=ArtifactType.TEST_RESULT,
        artifact_title="Validation result",
        schema=TestResultResponse,
        system_prompt_path="app/agents/prompts/tester.md",
        user_prompt_template=(
            "Return JSON with passed, summary, commands, and failures describing the "
            "validation strategy for this task. commands must contain only whitelist-safe "
            "commands: ruff check ., mypy app, pytest -q, pytest tests -q, or pytest "
            "<test-path> -q. Do not emit shell builtins, pipes, redirects, grep, find, "
            "test, python -c, bash, sh, awk, sed, curl, or compound commands:\n\n{request_text}"
        ),
    ),
]


class OrchestrationService:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._worker_threads and any(t.is_alive() for t in self._worker_threads):
            return

        settings = get_settings()
        settings.workspace_root_path.mkdir(parents=True, exist_ok=True)
        settings.backup_root_path.mkdir(parents=True, exist_ok=True)
        recovered_pending_runs = self._recover_interrupted_runs()
        provider_health = get_provider().health_check()
        if provider_health.status == ProviderStatus.UNAVAILABLE:
            logger.warning(
                "LM provider unavailable at orchestration startup; runs may fail until it "
                "recovers. detail=%s",
                provider_health.detail,
            )

        self._stop_event.clear()
        worker_count = max(1, int(settings.worker_count))
        self._worker_threads = []
        for index in range(worker_count):
            thread = threading.Thread(
                target=self._run_loop,
                name=f"orchestration-worker-{index}",
                daemon=True,
            )
            self._worker_threads.append(thread)
            thread.start()
        for run_id in recovered_pending_runs:
            self.enqueue_run(run_id)

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._worker_threads:
            if thread.is_alive():
                thread.join(timeout=30)
        self._worker_threads.clear()

    def enqueue_run(self, run_id: str) -> None:
        self._queue.put(run_id)

    def _recover_interrupted_runs(self) -> list[str]:
        session = get_session_factory()()
        try:
            interrupted_runs = session.scalars(
                select(RunModel).where(RunModel.status.in_([RunStatus.RUNNING, "queued"]))
            ).all()
            pending_runs = session.scalars(
                select(RunModel).where(RunModel.status == RunStatus.PENDING)
            ).all()

            for run in interrupted_runs:
                previous_status = str(run.status)
                run.status = RunStatus.FAILED
                run.error_message = (
                    "Run was recovered from an interrupted or legacy worker state. Retry it from "
                    "the UI/API to create a fresh workspace."
                )
                self._add_event(
                    session,
                    run.id,
                    "run_recovered_stale",
                    run.error_message,
                )
                self._record_state_snapshot(
                    session,
                    run,
                    self._build_state_for_stage(run, run.current_stage),
                    current_step="startup_recovery_failed",
                    payload={"previous_status": previous_status},
                )

            if interrupted_runs:
                session.commit()

            return [run.id for run in pending_runs]
        finally:
            session.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            try:
                self._process_run(run_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Run processing crashed for %s: %s", run_id, exc)
                self._mark_run_failed(run_id, str(exc))
            finally:
                self._queue.task_done()

    def _process_run(self, run_id: str) -> None:
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            if run is None:
                return
            if run.status == RunStatus.CANCELLED:
                return
            set_run_id(run.id)
            set_request_id(run.request_id)

            task = session.get(TaskModel, run.task_id)
            if task is None:
                run.status = RunStatus.FAILED
                run.error_message = "Task record is missing."
                session.commit()
                return

            workflow_state = self._build_workflow_state(run, task)

            if (task.source_repo_spec or "").strip():
                try:
                    validate_source_repo_spec(task.source_repo_spec.strip(), get_settings())
                except ConfigurationError as exc:
                    run.status = RunStatus.FAILED
                    run.current_stage = RunStage.INTAKE
                    run.error_message = str(exc)
                    self._add_event(session, run.id, "source_repo_invalid", str(exc))
                    session.commit()
                    return

            workspace_path = create_run_workspace(run.id, task)
            run.status = RunStatus.RUNNING
            self._add_event(
                session,
                run.id,
                "run_started",
                f"Worker started the run in {workspace_path}.",
            )
            self._record_state_snapshot(
                session,
                run,
                workflow_state,
                current_step="workspace_prepared",
                payload={"workspace_path": str(workspace_path)},
            )
            session.commit()

            if self._checkpoint_cancelled(session, run, "workspace_prepared"):
                return

            planner_stage = self._stage_by_name(RunStage.PLANNER)
            architect_stage = self._stage_by_name(RunStage.ARCHITECT)
            ui_designer_stage = self._stage_by_name(RunStage.UI_DESIGNER)
            coder_stage = self._stage_by_name(RunStage.CODER)
            reviewer_stage = self._stage_by_name(RunStage.REVIEWER)
            tester_stage = self._stage_by_name(RunStage.TESTER)

            planner_request = task.request_text
            settings = get_settings()
            if settings.use_scout_stage or task.use_scout:
                scout_block = self._build_scout_preamble(run.id)
                planner_request = f"{scout_block}\n\n{task.request_text}"

            planner_model = self._run_planner_with_guard(
                session=session,
                run=run,
                task=task,
                stage=planner_stage,
                request_text=planner_request,
                workflow_state=workflow_state,
            )
            if planner_model is None:
                return
            if self._checkpoint_cancelled(session, run, "planner_completed"):
                return
            workflow_state["planner_output"] = planner_model.model_dump_json()
            architect_model = cast(
                ArchitectureResponse,
                self._run_stage_with_provider_retries(
                    session,
                    run,
                    task,
                    architect_stage,
                    task.request_text,
                ),
            )
            if self._checkpoint_cancelled(session, run, "architect_completed"):
                return
            workflow_state["architecture_output"] = architect_model.model_dump_json()
            ui_design_model = cast(
                UIDesignResponse,
                self._run_stage_with_provider_retries(
                    session,
                    run,
                    task,
                    ui_designer_stage,
                    task.request_text,
                ),
            )
            if self._checkpoint_cancelled(session, run, "ui_designer_completed"):
                return
            workflow_state["ui_design_output"] = ui_design_model.model_dump_json()

            review_retries = 0
            test_retries = 0
            total_retries = 0
            retry_feedback: list[str] = []

            while True:
                if self._checkpoint_cancelled(session, run, "coder_loop_checkpoint"):
                    return
                coder_prompt = self._build_coder_request(
                    task.request_text,
                    run.id,
                    task.target_files,
                    planner_model,
                    architect_model,
                    ui_design_model,
                    retry_feedback,
                )
                try:
                    code_model = cast(
                        CodeChangeResponse,
                        self._run_stage(session, run, task, coder_stage, coder_prompt),
                    )
                except ProviderError as exc:
                    test_retries += 1
                    total_retries += 1
                    retry_feedback = [
                        f"Coder stage failed before producing a usable patch: {exc}",
                        "Return valid JSON only, matching the code_change schema.",
                    ]
                    run.retry_count = total_retries
                    workflow_state["retry_count"] = total_retries
                    workflow_state["errors"] = retry_feedback
                    self._add_event(
                        session,
                        run.id,
                        "coder_stage_failed",
                        "Coder stage failed before producing a usable patch; retrying coder stage.",
                        json.dumps({"failures": retry_feedback}, indent=2),
                    )
                    if self._should_block(run, review_retries, test_retries, total_retries):
                        if self._maybe_short_circuit_ui_noop(
                            session,
                            run,
                            task,
                            workflow_state,
                            "Coder stage retry threshold exceeded, but existing workspace already "
                            "satisfies UI contracts and validation.",
                        ):
                            return
                        self._block_run(
                            session,
                            run,
                            "Coder stage retry threshold exceeded.",
                            json.dumps({"failures": retry_feedback}, indent=2),
                        )
                        return

                    run.status = RunStatus.REVIEW_REQUIRED
                    run.error_message = "Coder stage failed before producing a usable patch."
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue
                workflow_state["code_output"] = code_model.model_dump_json()
                if self._checkpoint_cancelled(session, run, "code_model_generated"):
                    return
                try:
                    self._apply_code_changes(session, run, code_model)
                except PatchGuardError as exc:
                    test_retries += 1
                    total_retries += 1
                    retry_feedback = [str(exc)]
                    run.retry_count = total_retries
                    workflow_state["retry_count"] = total_retries
                    workflow_state["errors"] = retry_feedback
                    self._add_event(
                        session,
                        run.id,
                        "patch_guard_failed",
                        "AI-generated patch violated deterministic safety guards.",
                        json.dumps({"failures": retry_feedback}, indent=2),
                    )
                    if self._should_block(run, review_retries, test_retries, total_retries):
                        if self._maybe_short_circuit_ui_noop(
                            session,
                            run,
                            task,
                            workflow_state,
                            "Patch guard retry threshold exceeded, but existing workspace already "
                            "satisfies UI contracts and validation.",
                        ):
                            return
                        self._block_run(
                            session,
                            run,
                            "Patch guard retry threshold exceeded.",
                            json.dumps({"failures": retry_feedback}, indent=2),
                        )
                        return

                    run.status = RunStatus.REVIEW_REQUIRED
                    run.error_message = "AI-generated patch violated deterministic safety guards."
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue

                review_prompt = self._build_review_request(task.request_text, retry_feedback)
                review_model = cast(
                    ReviewResponse,
                    self._run_stage_with_provider_retries(
                        session,
                        run,
                        task,
                        reviewer_stage,
                        review_prompt,
                    ),
                )
                if self._checkpoint_cancelled(session, run, "review_completed"):
                    return
                workflow_state["review_output"] = review_model.model_dump_json()
                if not review_model.approved:
                    review_retries += 1
                    total_retries += 1
                    retry_feedback = [review_model.summary, *review_model.issues]
                    run.retry_count = total_retries
                    workflow_state["retry_count"] = total_retries
                    workflow_state["errors"] = retry_feedback
                    self._add_event(
                        session,
                        run.id,
                        "review_rejected",
                        "Reviewer rejected the current proposal; retrying coder stage.",
                        review_model.model_dump_json(),
                    )
                    if self._should_block(run, review_retries, test_retries, total_retries):
                        if self._maybe_short_circuit_ui_noop(
                            session,
                            run,
                            task,
                            workflow_state,
                            "Reviewer retry threshold exceeded, but existing workspace already "
                            "satisfies UI contracts and validation.",
                        ):
                            return
                        self._block_run(
                            session,
                            run,
                            "Reviewer rejection threshold exceeded.",
                            review_model.model_dump_json(),
                        )
                        return

                    run.status = RunStatus.REVIEW_REQUIRED
                    run.error_message = "Reviewer requested changes."
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue

                test_prompt = self._build_test_request(task.request_text, retry_feedback)
                test_model = cast(
                    TestResultResponse,
                    self._run_stage_with_provider_retries(
                        session,
                        run,
                        task,
                        tester_stage,
                        test_prompt,
                    ),
                )
                local_validation_passed, local_failures = self._run_local_validation(
                    session,
                    run,
                    test_model,
                )
                if self._checkpoint_cancelled(session, run, "tester_completed"):
                    return
                workflow_state["test_output"] = test_model.model_dump_json()
                if not test_model.passed or not local_validation_passed:
                    test_retries += 1
                    total_retries += 1
                    retry_feedback = [test_model.summary, *test_model.failures, *local_failures]
                    run.retry_count = total_retries
                    workflow_state["retry_count"] = total_retries
                    workflow_state["errors"] = retry_feedback
                    self._add_event(
                        session,
                        run.id,
                        "tests_failed",
                        "Validation stage reported failures; retrying coder stage.",
                        test_model.model_dump_json(),
                    )
                    if self._should_block(run, review_retries, test_retries, total_retries):
                        if self._maybe_short_circuit_ui_noop(
                            session,
                            run,
                            task,
                            workflow_state,
                            "Validation retry threshold exceeded, but existing workspace already "
                            "satisfies UI contracts and validation.",
                        ):
                            return
                        self._block_run(
                            session,
                            run,
                            "Validation retry threshold exceeded.",
                            test_model.model_dump_json(),
                        )
                        return

                    run.status = RunStatus.REVIEW_REQUIRED
                    run.error_message = "Validation stage reported failures."
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue

                break

            run.retry_count = total_retries
            run.status = RunStatus.AWAITING_APPROVAL
            run.current_stage = RunStage.APPROVAL
            run.error_message = None
            workflow_state["status"] = RunStatus.AWAITING_APPROVAL
            workflow_state["stage"] = RunStage.APPROVAL
            workflow_state["retry_count"] = total_retries
            self._add_event(
                session,
                run.id,
                "awaiting_approval",
                "Run is awaiting operator approval before any git-side effects.",
            )
            self._record_state_snapshot(
                session,
                run,
                workflow_state,
                current_step="awaiting_operator_approval",
                payload={"retry_count": total_retries},
            )
            session.commit()
        except ProviderError as exc:
            run = session.get(RunModel, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.current_stage = run.current_stage or RunStage.INTAKE
                run.error_message = str(exc)
                self._add_event(session, run.id, "provider_failed", str(exc))
                session.commit()
        finally:
            set_run_id(None)
            set_request_id(None)
            session.close()

    def _stage_by_name(self, stage_name: RunStage) -> StageDefinition:
        for stage in STAGES:
            if stage.stage == stage_name:
                return stage
        raise ProviderError(f"Stage definition missing for {stage_name}.")

    def _build_scout_preamble(self, run_id: str) -> str:
        snapshot = list_run_workspace_files(run_id)
        files = snapshot.get("files") if isinstance(snapshot, dict) else []
        if not isinstance(files, list):
            files = []
        trimmed = [str(f) for f in files[:120]]
        lines = "\n".join(f"- {path}" for path in trimmed)
        return (
            "Scout: repository file tree (read-only, truncated). Use it to orient the plan.\n"
            f"{lines}"
        )

    def _run_stage(
        self,
        session,
        run: RunModel,
        task: TaskModel,
        stage: StageDefinition,
        request_text: str,
        timeout_seconds: Optional[float] = None,
    ) -> BaseModel:
        settings = get_settings()
        model_name = effective_lmstudio_model_for_stage(task, stage.stage, settings)
        provider = resolve_provider(task.provider_override, model_name)
        run.current_stage = stage.stage
        stage_name = stage.stage.value
        self._add_event(session, run.id, f"{stage_name}_started", f"Started {stage_name} stage.")
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, stage.stage),
            current_step=f"{stage_name}_started",
            payload={"stage": stage_name},
        )
        session.commit()

        model = self._invoke_stage(
            session,
            task,
            provider,
            stage,
            request_text,
            timeout_seconds=timeout_seconds,
        )
        session.add(
            self._make_artifact(
                run.id,
                stage.artifact_type,
                stage.artifact_title,
                model,
            )
        )
        self._add_event(
            session,
            run.id,
            f"{stage_name}_completed",
            f"Completed {stage_name} stage.",
            model.model_dump_json(),
        )
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, stage.stage),
            current_step=f"{stage_name}_completed",
            payload=model.model_dump(),
        )
        session.commit()
        return model

    def _run_stage_with_provider_retries(
        self,
        session,
        run: RunModel,
        task: TaskModel,
        stage: StageDefinition,
        request_text: str,
        attempts: int = 3,
    ) -> BaseModel:
        current_request = request_text
        stage_name = stage.stage.value
        for attempt in range(1, attempts + 1):
            if self._checkpoint_cancelled(session, run, f"{stage_name}_retry_checkpoint"):
                raise WorkflowError("Run cancelled by operator.")
            try:
                return self._run_stage(session, run, task, stage, current_request)
            except (ProviderError, ValidationError) as exc:
                if attempt >= attempts or not self._is_retryable_stage_output_error(exc):
                    raise

                feedback = (
                    f"{stage_name} stage returned invalid structured output on attempt "
                    f"{attempt}/{attempts}: {exc}"
                )
                self._add_event(
                    session,
                    run.id,
                    f"{stage_name}_retry",
                    "Stage returned invalid structured output; retrying with stricter JSON "
                    "instructions.",
                    json.dumps({"attempt": attempt, "error": str(exc)}, indent=2),
                )
                session.commit()
                current_request = (
                    f"{request_text}\n\nRetry feedback:\n"
                    f"- {feedback}\n"
                    "- Return valid JSON only.\n"
                    "- Do not include Markdown fences, comments, trailing commas, or prose outside "
                    "the JSON object.\n"
                    "- Ensure every required key matches the requested schema."
                )

        raise ProviderError(f"{stage_name} stage failed to return valid structured output.")

    def _checkpoint_cancelled(self, session, run: RunModel, step: str) -> bool:
        session.refresh(run)
        if run.status != RunStatus.CANCELLED:
            return False
        if not run.error_message:
            run.error_message = "Run cancelled by operator."
        self._add_event(
            session,
            run.id,
            "run_cancelled_checkpoint",
            f"Cancellation checkpoint reached at {step}.",
        )
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, run.current_stage),
            current_step="cancelled",
            payload={"checkpoint": step},
        )
        session.commit()
        return True

    def _is_retryable_stage_output_error(self, exc: Exception) -> bool:
        if isinstance(exc, ValidationError):
            return True
        if not isinstance(exc, ProviderError):
            return False
        message = str(exc).lower()
        return any(
            phrase in message
            for phrase in (
                "malformed json",
                "invalid json",
                "schema",
                "validation",
                "valid json",
            )
        )

    def _apply_code_changes(
        self,
        session,
        run: RunModel,
        code_model: CodeChangeResponse,
    ) -> None:
        if not code_model.line_changes and not code_model.file_changes:
            self._add_event(
                session,
                run.id,
                "code_patch_skipped",
                "Coder response did not include line_changes or file_changes; no workspace "
                "files were modified.",
            )
            session.commit()
            return

        code_model = self._drop_invalid_route_change(session, run, code_model)
        self._validate_patch_scope(run, code_model)
        self._validate_patch_intent(run, code_model)
        self._validate_line_change_targets(code_model)
        self._validate_route_contract(run.id, code_model)
        self._validate_render_contract(run.id, code_model)

        applied = []
        for line_change in code_model.line_changes:
            applied.append(self._apply_line_change(run.id, line_change))
        for file_change in code_model.file_changes:
            applied.append(self._apply_file_change(run.id, file_change))

        diff = get_run_workspace_diff(run.id)
        self._add_event(
            session,
            run.id,
            "code_patch_applied",
            f"Applied {len(applied)} AI-generated change(s) to the run workspace.",
            json.dumps({"applied": applied, "changed_files": diff["changed_files"]}, indent=2),
        )
        session.add(
            self._make_log_artifact(
                run.id,
                "Applied code patch",
                {
                    "applied": applied,
                    "diff": diff,
                },
            )
        )
        session.commit()

    def _drop_invalid_route_change(
        self,
        session,
        run: RunModel,
        code_model: CodeChangeResponse,
    ) -> CodeChangeResponse:
        route_change = self._route_file_change(code_model)
        if route_change is None:
            return code_model

        try:
            self._validate_route_file_change(run.id, route_change)
            return code_model
        except PatchGuardError:
            non_route_changes = [
                item
                for item in code_model.file_changes
                if item.path.strip().lstrip("/") != "app/ui/routes.py"
            ]
            if not non_route_changes:
                raise

            self._add_event(
                session,
                run.id,
                "route_patch_dropped",
                "Dropped unsafe app/ui/routes.py edit and kept remaining file changes.",
            )
            return code_model.model_copy(
                update={
                    "file_changes": non_route_changes,
                    "changed_files": [
                        item
                        for item in code_model.changed_files
                        if item.strip().lstrip("/") != "app/ui/routes.py"
                    ],
                }
            )

    def _validate_patch_scope(self, run: RunModel, code_model: CodeChangeResponse) -> None:
        target_files = set(run.task.target_files if run.task is not None else [])
        if not target_files:
            return

        changed_paths = [
            *(item.path for item in code_model.line_changes),
            *(item.path for item in code_model.file_changes),
        ]
        blocked_paths = [
            path for path in changed_paths if not self._path_allowed_by_targets(path, target_files)
        ]
        if blocked_paths:
            allowed = ", ".join(sorted(target_files))
            blocked = ", ".join(sorted(blocked_paths))
            raise PatchGuardError(
                f"Patch touched files outside task target_files. Allowed: {allowed}. "
                f"Blocked: {blocked}."
            )

    def _path_allowed_by_targets(self, path: str, target_files: set[str]) -> bool:
        normalized_path = path.strip().lstrip("/")
        for target in target_files:
            normalized_target = target.strip().lstrip("/")
            if normalized_path == normalized_target:
                return True
            if normalized_target.endswith("/") and normalized_path.startswith(normalized_target):
                return True
        return False

    def _validate_patch_intent(self, run: RunModel, code_model: CodeChangeResponse) -> None:
        task = run.task
        if task is None:
            return

        request_text = f"{task.title}\n{task.request_text}\n{' '.join(task.constraints)}".lower()
        is_doc_task = (task.task_type or "").lower() in {"doc", "docs", "documentation"}
        asks_for_tiny_change = any(
            phrase in request_text
            for phrase in (
                "one short sentence",
                "one sentence",
                "tiny",
                "small controlled",
                "documentation-only",
                "wording",
            )
        )
        if not (is_doc_task or asks_for_tiny_change):
            return

        for file_change in code_model.file_changes:
            normalized_path = file_change.path.strip().lstrip("/")
            if not normalized_path.lower().endswith((".md", ".txt", ".rst")):
                continue
            if file_change.change_type != "upsert":
                continue

            existing_path = get_run_workspace_path(run.id) / normalized_path
            if not existing_path.exists():
                continue

            original_lines = existing_path.read_text(encoding="utf-8").splitlines()
            proposed_lines = file_change.content.splitlines()
            if not original_lines:
                continue

            deleted, inserted = self._line_delta_counts(original_lines, proposed_lines)
            changed = deleted + inserted
            deletion_ratio = deleted / max(len(original_lines), 1)
            changed_ratio = changed / max(len(original_lines), 1)
            allowed_insertions = 6 if asks_for_tiny_change else max(12, len(original_lines) // 4)
            allowed_deletions = 0 if asks_for_tiny_change else max(4, len(original_lines) // 10)

            if (
                inserted > allowed_insertions
                or deleted > allowed_deletions
                or deletion_ratio > 0.15
                or changed_ratio > 0.35
            ):
                raise PatchGuardError(
                    "Patch is too large for the requested documentation intent. "
                    f"{normalized_path}: inserted={inserted}, deleted={deleted}, "
                    f"original_lines={len(original_lines)}. Keep the change narrowly scoped."
                )

        for line_change in code_model.line_changes:
            normalized_path = line_change.path.strip().lstrip("/")
            if not normalized_path.lower().endswith((".md", ".txt", ".rst")):
                continue
            inserted = len(line_change.content.splitlines()) if line_change.content else 0
            if inserted > 6:
                raise PatchGuardError(
                    "Line-level patch is too large for the requested documentation intent. "
                    f"{normalized_path}: inserted={inserted}. Keep the change narrowly scoped."
                )
            if line_change.operation == "delete" and not any(
                phrase in request_text for phrase in ("delete", "remove")
            ):
                raise PatchGuardError(
                    "Line-level patch attempted to delete documentation content without an "
                    "explicit delete/remove request."
                )

    def _line_delta_counts(
        self,
        original_lines: list[str],
        proposed_lines: list[str],
    ) -> tuple[int, int]:
        prefix = 0
        max_prefix = min(len(original_lines), len(proposed_lines))
        while prefix < max_prefix and original_lines[prefix] == proposed_lines[prefix]:
            prefix += 1

        original_suffix = len(original_lines)
        proposed_suffix = len(proposed_lines)
        while (
            original_suffix > prefix
            and proposed_suffix > prefix
            and original_lines[original_suffix - 1] == proposed_lines[proposed_suffix - 1]
        ):
            original_suffix -= 1
            proposed_suffix -= 1

        return original_suffix - prefix, proposed_suffix - prefix

    def _validate_route_contract(self, run_id: str, code_model: CodeChangeResponse) -> None:
        route_change = self._route_file_change(code_model)
        if route_change is None:
            return
        self._validate_route_file_change(run_id, route_change)

    def _route_file_change(self, code_model: CodeChangeResponse) -> Optional[FileChange]:
        return next(
            (
                item
                for item in code_model.file_changes
                if item.path.strip().lstrip("/") == "app/ui/routes.py"
            ),
            None,
        )

    def _validate_line_change_targets(self, code_model: CodeChangeResponse) -> None:
        protected_files = {"app/ui/routes.py", "app/ui/render.py"}
        blocked = sorted(
            {
                item.path.strip().lstrip("/")
                for item in code_model.line_changes
                if item.path.strip().lstrip("/") in protected_files
            }
        )
        if blocked:
            raise PatchGuardError(
                "Line-level patches are not allowed for protected UI route/render files. "
                f"Use scoped file_changes preserving contracts instead: {', '.join(blocked)}."
            )

    def _validate_route_file_change(self, run_id: str, route_change: FileChange) -> None:
        if route_change.change_type == "delete":
            raise PatchGuardError("Patch attempted to delete app/ui/routes.py.")

        route_path = get_run_workspace_path(run_id) / "app/ui/routes.py"
        if not route_path.exists():
            return

        baseline = self._route_signatures(route_path.read_text(encoding="utf-8"))
        proposed = self._route_signatures(route_change.content)
        if proposed != baseline:
            raise PatchGuardError(
                "Patch changed app/ui/routes.py route signatures. Preserve existing route "
                "decorators, paths, function names, and parameters."
            )

    def _validate_render_contract(self, run_id: str, code_model: CodeChangeResponse) -> None:
        render_change = next(
            (
                item
                for item in code_model.file_changes
                if item.path.strip().lstrip("/") == "app/ui/render.py"
            ),
            None,
        )
        if render_change is None:
            return
        if render_change.change_type == "delete":
            raise PatchGuardError("Patch attempted to delete app/ui/render.py.")

        render_path = get_run_workspace_path(run_id) / "app/ui/render.py"
        if not render_path.exists():
            return

        required_names = {"layout", "page", "page_with_auto_refresh", "status_badge"}
        baseline = self._function_signatures(
            render_path.read_text(encoding="utf-8"), required_names
        )
        proposed = self._function_signatures(render_change.content, required_names)
        if proposed != baseline:
            missing = sorted(set(baseline) - set(proposed))
            details = f" Missing: {', '.join(missing)}." if missing else ""
            raise PatchGuardError(
                "Patch changed app/ui/render.py public helper contract. Preserve existing "
                "function names and parameters for layout, page, page_with_auto_refresh, "
                f"and status_badge.{details}"
            )

    def _function_signatures(self, source: str, names: set[str]) -> dict[str, str]:
        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            raise PatchGuardError(f"Python file is not valid Python: {exc.msg}.") from exc
        signatures: dict[str, str] = {}
        for node in module.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                signatures[node.name] = ast.unparse(node.args)
        return signatures

    def _route_signatures(self, source: str) -> list[tuple[str, str, str, str]]:
        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            raise PatchGuardError(f"app/ui/routes.py is not valid Python: {exc.msg}.") from exc

        signatures: list[tuple[str, str, str, str]] = []
        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                route = self._route_decorator(decorator)
                if route is None:
                    continue
                method, path = route
                signatures.append((method, path, node.name, ast.unparse(node.args)))
        return signatures

    def _route_decorator(self, decorator: ast.expr) -> Optional[tuple[str, str]]:
        if not isinstance(decorator, ast.Call):
            return None
        func = decorator.func
        if not isinstance(func, ast.Attribute):
            return None
        if func.attr not in {"get", "post", "put", "patch", "delete"}:
            return None
        if not isinstance(func.value, ast.Name) or func.value.id != "router":
            return None
        if not decorator.args:
            return None
        path_arg = decorator.args[0]
        if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
            return None
        return func.attr, path_arg.value

    def _apply_file_change(self, run_id: str, file_change: FileChange) -> dict[str, object]:
        if file_change.change_type == "delete":
            result = delete_run_workspace_file(run_id, file_change.path)
            return {
                "path": file_change.path,
                "change_type": file_change.change_type,
                "deleted": bool(result["deleted"]),
            }

        write_run_workspace_file(run_id, file_change.path, file_change.content)
        return {
            "path": file_change.path,
            "change_type": file_change.change_type,
            "bytes": len(file_change.content.encode("utf-8")),
        }

    def _apply_line_change(self, run_id: str, line_change: LineChange) -> dict[str, object]:
        normalized_path = line_change.path.strip().lstrip("/")
        file_path = get_run_workspace_path(run_id) / normalized_path
        if not file_path.exists():
            raise PatchGuardError(f"Line-level patch target does not exist: {normalized_path}.")
        if not file_path.is_file():
            raise PatchGuardError(f"Line-level patch target is not a file: {normalized_path}.")

        original_text = file_path.read_text(encoding="utf-8")
        had_trailing_newline = original_text.endswith("\n")
        lines = original_text.splitlines()
        matches = [index for index, line in enumerate(lines) if line == line_change.anchor]
        if line_change.occurrence > len(matches):
            raise PatchGuardError(
                "Line-level patch anchor was not found with the requested occurrence. "
                f"{normalized_path}: occurrence={line_change.occurrence}."
            )

        line_index = matches[line_change.occurrence - 1]
        content_lines = line_change.content.splitlines()
        if line_change.operation == "replace":
            lines[line_index : line_index + 1] = content_lines
        elif line_change.operation == "insert_after":
            lines[line_index + 1 : line_index + 1] = content_lines
        elif line_change.operation == "insert_before":
            lines[line_index:line_index] = content_lines
        elif line_change.operation == "delete":
            if line_change.content:
                raise PatchGuardError("Line-level delete patches must not include content.")
            del lines[line_index]
        else:  # pragma: no cover - pydantic validates allowed operations.
            raise PatchGuardError(
                f"Unsupported line-level patch operation: {line_change.operation}."
            )

        new_text = "\n".join(lines)
        if had_trailing_newline or new_text:
            new_text += "\n"
        write_run_workspace_file(run_id, normalized_path, new_text)
        return {
            "path": normalized_path,
            "change_type": "line",
            "operation": line_change.operation,
            "line_number": line_index + 1,
            "bytes": len(line_change.content.encode("utf-8")),
        }

    def _run_local_validation(
        self,
        session,
        run: RunModel,
        test_model: TestResultResponse,
    ) -> tuple[bool, list[str]]:
        commands = self._validation_commands(test_model.commands, get_run_workspace_path(run.id))
        if not commands:
            self._add_event(
                session,
                run.id,
                "validation_skipped",
                "Tester response did not include runnable validation commands.",
            )
            session.commit()
            return True, []

        results: list[dict[str, object]] = []
        failures: list[str] = []
        for command in commands:
            try:
                result = run_validation_command(command, cwd=get_run_workspace_path(run.id))
            except ConfigurationError as exc:
                results.append(
                    {
                        "command": command,
                        "returncode": 126,
                        "stdout": "",
                        "stderr": str(exc),
                        "timed_out": False,
                    }
                )
                failures.append(str(exc))
                continue

            payload = self._command_result_payload(result)
            results.append(payload)
            if result.returncode != 0:
                failures.append(
                    f"{' '.join(result.command)} failed with exit code {result.returncode}."
                )

        passed = not failures
        self._add_event(
            session,
            run.id,
            "validation_commands_completed",
            "Local validation commands completed." if passed else "Local validation failed.",
            json.dumps({"passed": passed, "results": results}, indent=2),
        )
        session.add(
            self._make_log_artifact(
                run.id,
                "Local validation commands",
                {"passed": passed, "results": results},
            )
        )
        session.commit()
        return passed, failures

    def _validation_commands(self, commands: list[str], workspace_path: Path) -> list[list[str]]:
        parsed = [shlex.split(command) for command in commands if command.strip()]
        if parsed:
            return parsed

        if (workspace_path / "pyproject.toml").exists():
            return [["ruff", "check", "."], ["mypy", "app"], ["pytest", "-q"]]
        return []

    def _command_result_payload(self, result: CommandResult) -> dict[str, object]:
        return {
            "command": result.command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }

    def _make_log_artifact(
        self,
        run_id: str,
        title: str,
        payload: dict[str, object],
    ) -> ArtifactModel:
        settings = get_settings()
        content = json.dumps(payload, indent=2)
        truncated = False
        if len(content) > settings.artifact_char_limit:
            content = content[: settings.artifact_char_limit] + "\n... [truncated]"
            truncated = True
        return ArtifactModel(
            run_id=run_id,
            artifact_type=ArtifactType.LOG,
            title=title,
            content=content,
            truncated=truncated,
        )

    def _should_block(
        self,
        run: RunModel,
        review_retries: int,
        test_retries: int,
        total_retries: int,
    ) -> bool:
        return (
            review_retries >= MAX_REVIEW_RETRIES
            or test_retries >= MAX_TEST_RETRIES
            or total_retries >= MAX_TOTAL_RETRIES
        )

    def _block_run(self, session, run: RunModel, message: str, payload_json: str) -> None:
        run.status = RunStatus.BLOCKED
        run.current_stage = RunStage.CODER
        run.error_message = message
        self._add_event(session, run.id, "run_blocked", message, payload_json)
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, RunStage.CODER),
            current_step="run_blocked",
            payload={"message": message, "details": payload_json},
        )
        session.commit()

    def _maybe_short_circuit_ui_noop(
        self,
        session,
        run: RunModel,
        task: TaskModel,
        workflow_state: WorkflowState,
        reason: str,
    ) -> bool:
        if not self._is_ui_task(task):
            return False

        diff = get_run_workspace_diff(run.id)
        if bool(diff.get("has_changes")):
            return False

        commands = [["ruff", "check", "."], ["mypy", "app"], ["pytest", "-q"]]
        command_results: list[dict[str, object]] = []
        for command in commands:
            result = run_validation_command(command, cwd=get_run_workspace_path(run.id))
            command_results.append(self._command_result_payload(result))
            if result.returncode != 0:
                return False

        code_model = CodeChangeResponse(
            changed_files=[],
            implementation_notes=[
                "No workspace code changes required. Existing UI implementation already satisfies "
                "route/render contracts and validation."
            ],
            requires_operator_approval=False,
            file_changes=[],
        )
        review_model = ReviewResponse(
            approved=True,
            summary="No additional code changes required for this UI task.",
            issues=[],
        )
        test_model = TestResultResponse(
            passed=True,
            summary="No-op completion confirmed by local validation commands.",
            commands=["ruff check .", "mypy app", "pytest -q"],
            failures=[],
        )

        session.add(
            self._make_artifact(
                run.id,
                ArtifactType.CODE_CHANGE,
                "Proposed code change",
                code_model,
            )
        )
        session.add(self._make_artifact(run.id, ArtifactType.REVIEW, "Review result", review_model))
        session.add(
            self._make_artifact(
                run.id,
                ArtifactType.TEST_RESULT,
                "Validation result",
                test_model,
            )
        )
        session.add(
            self._make_log_artifact(
                run.id,
                "Local validation commands",
                {"passed": True, "results": command_results},
            )
        )
        self._add_event(
            session,
            run.id,
            "noop_ui_completion",
            reason,
            json.dumps({"validation": command_results}, indent=2),
        )

        run.status = RunStatus.AWAITING_APPROVAL
        run.current_stage = RunStage.APPROVAL
        run.error_message = None
        workflow_state["status"] = RunStatus.AWAITING_APPROVAL
        workflow_state["stage"] = RunStage.APPROVAL
        self._add_event(
            session,
            run.id,
            "awaiting_approval",
            "Run is awaiting operator approval before any git-side effects.",
        )
        self._record_state_snapshot(
            session,
            run,
            workflow_state,
            current_step="awaiting_operator_approval",
            payload={"reason": reason, "no_op": True},
        )
        session.commit()
        return True

    def _is_ui_task(self, task: TaskModel) -> bool:
        target_files = set(task.target_files)
        return bool(target_files) and target_files.issubset(
            {"app/ui/render.py", "app/ui/routes.py"}
        )

    def _add_event(
        self,
        session,
        run_id: str,
        event_type: str,
        message: str,
        payload_json: Optional[str] = None,
    ) -> None:
        session.add(
            RunEventModel(
                run_id=run_id,
                event_type=event_type,
                message=message,
                payload_json=payload_json,
            )
        )

    def _build_coder_request(
        self,
        request_text: str,
        run_id: str,
        target_files: list[str],
        planner_model: PlanResponse,
        architect_model: ArchitectureResponse,
        ui_design_model: UIDesignResponse,
        retry_feedback: list[str],
    ) -> str:
        sections = [
            request_text,
            "\nCoder hard constraints:",
            "- Preserve existing FastAPI APIRouter setup, route paths, route function names, "
            "imports, form parameters, redirects, auth/session checks, and API/service calls.",
            "- Do not create a standalone FastAPI() app in app/ui/routes.py.",
            "- Do not remove existing UI flows: login, dashboard, repository, provider, "
            "settings, backups, run detail, run actions, workspace diff, workspace editor, "
            "and backup restore rehearsal.",
            "- Keep changes scoped to existing UI rendering and styling unless a route-level "
            "change is strictly necessary.",
            "- If app/ui/render.py is in target_files, implement the visual redesign there first "
            "and do not edit app/ui/routes.py unless the requested behavior cannot work without "
            "it.",
            "- Return valid JSON only. Do not include Markdown fences, prose outside JSON, or "
            "comments.",
        ]
        if target_files:
            sections.extend(
                [
                    "\nTask target_files allowlist:",
                    *[f"- {item}" for item in target_files],
                    "Do not include line_changes or file_changes outside this allowlist.",
                ]
            )
        target_file_context = self._target_file_anchor_context(run_id, target_files)
        if target_file_context:
            sections.extend(
                [
                    "\nTarget file anchor context:",
                    target_file_context,
                    "For line_changes, choose anchor values from the exact file lines above. "
                    "Do not include the numeric prefix in the anchor string.",
                ]
            )
        route_contract = self._route_contract_prompt(run_id)
        if route_contract:
            sections.extend(["\nExisting app/ui/routes.py route contract:", route_contract])
        render_contract = self._render_contract_prompt(run_id)
        if render_contract:
            sections.extend(
                ["\nExisting app/ui/render.py public helper contract:", render_contract]
            )
        if retry_feedback:
            sections.extend(["\nRetry feedback:", *[f"- {item}" for item in retry_feedback]])
        sections.extend(
            [
                "\nImplementation guidance:",
                "- For visual redesign tasks, prefer app/ui/render.py edits and existing CSS/HTML "
                "helpers.",
                "- Avoid editing app/ui/routes.py unless the exact route contract above is "
                "preserved.",
                "- If a guard rejected a previous route edit, remove the route edit and make the "
                "visual change in app/ui/render.py instead.",
                "- Before returning JSON, mentally check Python string quoting for embedded HTML.",
                "\nPlanner summary:",
                planner_model.summary,
                "\nPlanner acceptance criteria:",
                *self._bullet_lines(planner_model.acceptance_criteria),
                "\nArchitecture plan:",
                *self._bullet_lines(architect_model.file_change_plan),
                "\nUI design direction:",
                ui_design_model.design_summary,
                "\nUI implementation notes:",
                *self._bullet_lines(ui_design_model.implementation_notes),
            ]
        )
        return "\n".join(sections)

    def _bullet_lines(self, values: list[str]) -> list[str]:
        return [f"- {value}" for value in values[:8]]

    def _target_file_anchor_context(self, run_id: str, target_files: list[str]) -> str:
        if not target_files:
            return ""

        workspace_path = get_run_workspace_path(run_id)
        context_blocks: list[str] = []
        for raw_path in target_files[:5]:
            normalized_path = raw_path.strip().lstrip("/")
            if normalized_path.endswith("/"):
                continue
            file_path = workspace_path / normalized_path
            if not file_path.exists() or not file_path.is_file():
                continue
            try:
                file_text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            lines = file_text.splitlines()
            if len(lines) > 80:
                preview_lines = [*lines[:40], "...", *lines[-20:]]
            else:
                preview_lines = lines
            numbered_lines = [
                f"{index + 1}: {line}" for index, line in enumerate(preview_lines)
            ]
            context_blocks.append(f"{normalized_path}:\n" + "\n".join(numbered_lines))
        return "\n\n".join(context_blocks)

    def _route_contract_prompt(self, run_id: str) -> str:
        route_path = get_run_workspace_path(run_id) / "app/ui/routes.py"
        if not route_path.exists():
            return ""
        signatures = self._route_signatures(route_path.read_text(encoding="utf-8"))
        if not signatures:
            return ""
        return "\n".join(
            f"- {method.upper()} {path}: def {name}({args})"
            for method, path, name, args in signatures
        )

    def _render_contract_prompt(self, run_id: str) -> str:
        render_path = get_run_workspace_path(run_id) / "app/ui/render.py"
        if not render_path.exists():
            return ""
        signatures = self._function_signatures(
            render_path.read_text(encoding="utf-8"),
            {"layout", "page", "page_with_auto_refresh", "status_badge"},
        )
        if not signatures:
            return ""
        return "\n".join(f"- def {name}({args})" for name, args in sorted(signatures.items()))

    def _build_review_request(self, request_text: str, retry_feedback: list[str]) -> str:
        if not retry_feedback:
            return request_text
        return "\n".join(
            [request_text, "Focus review on prior issues being resolved:", *retry_feedback]
        )

    def _build_test_request(self, request_text: str, retry_feedback: list[str]) -> str:
        whitelist_note = (
            "Validation command whitelist: commands may only be one of 'ruff check .', "
            "'mypy app', 'pytest -q', 'pytest tests -q', or 'pytest <test-path> -q'. "
            "Do not put grep, find, test, python -c, shell pipelines, redirects, bash, sh, "
            "awk, sed, or curl in commands."
        )
        if not retry_feedback:
            return "\n".join([request_text, whitelist_note])
        return "\n".join(
            [
                request_text,
                whitelist_note,
                "Focus validation on prior failures being resolved:",
                *retry_feedback,
            ]
        )

    def _invoke_stage(
        self,
        session,
        task: TaskModel,
        provider,
        stage: StageDefinition,
        request_text: str,
        timeout_seconds: Optional[float] = None,
    ) -> BaseModel:
        prompt_path = Path(stage.system_prompt_path)
        system_prompt = prompt_path.read_text(encoding="utf-8").strip()
        repo_key = repo_key_for_source_spec(task.source_repo_spec)
        overlay = load_active_playbook_overlay(session, repo_key, stage.stage)
        if overlay:
            system_prompt = f"{system_prompt}\n\n--- Approved playbook overlay ---\n{overlay}"
        user_prompt = stage.user_prompt_template.format(request_text=request_text)
        if stage.stage == RunStage.PLANNER:
            user_prompt = load_lessons_prompt_prefix(session, repo_key) + user_prompt
        if timeout_seconds is None:
            return self._complete_stage(provider, stage, system_prompt, user_prompt)
        if provider.__class__.__name__ == "LMStudioProvider":
            model_name = getattr(getattr(provider, "settings", None), "lmstudio_model", None)
            raw = self._invoke_stage_in_subprocess(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=timeout_seconds,
                provider_name="lmstudio",
                model_name=model_name,
            )
            payload = self._load_stage_json(raw, stage.stage)
            return stage.schema.model_validate(payload)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._complete_stage,
            provider,
            stage,
            system_prompt,
            user_prompt,
        )
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise StageTimeoutError(
                f"{stage.stage} stage timed out after {timeout_seconds:.1f} seconds.",
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _invoke_stage_in_subprocess(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float,
        provider_name: Optional[str],
        model_name: Optional[str],
    ) -> str:
        payload = json.dumps(
            {
                "provider_name": provider_name,
                "model_name": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "app.services.provider_stage_runner"],
                input=payload,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise StageTimeoutError(
                f"Planner stage timed out after {timeout_seconds:.1f} seconds."
            ) from err
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "unknown runner error"
            raise ProviderError(f"Planner subprocess failed: {stderr}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("Planner subprocess returned invalid JSON.") from exc
        if not bool(result.get("ok", False)):
            raise ProviderError(str(result.get("error", "Planner subprocess failed.")))
        raw = result.get("raw")
        if not isinstance(raw, str):
            raise ProviderError("Planner subprocess returned an invalid payload.")
        return raw

    def _complete_stage(
        self,
        provider,
        stage: StageDefinition,
        system_prompt: str,
        user_prompt: str,
    ) -> BaseModel:
        raw = provider.structured_completion(system_prompt, user_prompt)
        payload = self._load_stage_json(raw, stage.stage)
        return stage.schema.model_validate(payload)

    def _load_stage_json(self, raw: str, stage_name: RunStage) -> object:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{stage_name} stage returned malformed JSON at line {exc.lineno}, "
                f"column {exc.colno}."
            ) from exc

    def _run_planner_with_guard(
        self,
        session,
        run: RunModel,
        task: TaskModel,
        stage: StageDefinition,
        request_text: str,
        workflow_state: WorkflowState,
    ) -> Optional[PlanResponse]:
        settings = get_settings()
        timeout_seconds = settings.planner_stage_timeout_seconds
        max_retries = max(settings.planner_stage_max_retries, 0)
        attempts_allowed = max_retries + 1
        self._add_event(
            session,
            run.id,
            "planner_guard_config",
            (
                f"Planner guard active timeout={timeout_seconds:.1f}s "
                f"attempts={attempts_allowed}."
            ),
        )
        session.commit()

        for attempt in range(1, attempts_allowed + 1):
            try:
                return cast(
                    PlanResponse,
                    self._run_stage(
                        session,
                        run,
                        task,
                        stage,
                        request_text,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            except StageTimeoutError:
                run.retry_count += 1
                workflow_state["retry_count"] = run.retry_count
                timeout_message = (
                    f"Planner stage timed out after {timeout_seconds:.1f}s "
                    f"(attempt {attempt}/{attempts_allowed})."
                )
                self._add_event(session, run.id, "planner_timeout", timeout_message)
                self._record_state_snapshot(
                    session,
                    run,
                    self._build_state_for_stage(run, RunStage.PLANNER),
                    current_step="planner_timeout",
                    payload={
                        "attempt": attempt,
                        "attempts_allowed": attempts_allowed,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                if attempt < attempts_allowed:
                    self._add_event(
                        session,
                        run.id,
                        "planner_retry",
                        f"Retrying planner stage (attempt {attempt + 1}/{attempts_allowed}).",
                    )
                    session.commit()
                    continue

                run.status = RunStatus.FAILED
                run.current_stage = RunStage.PLANNER
                run.error_message = "Planner stage timed out and retries were exhausted."
                self._add_event(session, run.id, "planner_failed", run.error_message)
                self._record_state_snapshot(
                    session,
                    run,
                    self._build_state_for_stage(run, RunStage.PLANNER),
                    current_step="planner_failed",
                    payload={
                        "attempts_allowed": attempts_allowed,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                session.commit()
                return None

        return None

    def _make_artifact(
        self,
        run_id: str,
        artifact_type: ArtifactType,
        title: str,
        model: BaseModel,
    ) -> ArtifactModel:
        settings = get_settings()
        content = json.dumps(model.model_dump(), indent=2)
        truncated = False
        if len(content) > settings.artifact_char_limit:
            content = content[: settings.artifact_char_limit] + "\n... [truncated]"
            truncated = True
        return ArtifactModel(
            run_id=run_id,
            artifact_type=artifact_type,
            title=title,
            content=content,
            truncated=truncated,
        )

    def _mark_run_failed(self, run_id: str, message: str) -> None:
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            if run is None:
                return
            set_run_id(run.id)
            set_request_id(run.request_id)
            run.status = RunStatus.FAILED
            run.error_message = message
            self._add_event(session, run_id, "run_failed", message)
            self._record_state_snapshot(
                session,
                run,
                self._build_state_for_stage(run, run.current_stage),
                current_step="run_failed",
                payload={"message": message},
            )
            session.commit()
        finally:
            set_run_id(None)
            set_request_id(None)
            session.close()

    def _build_workflow_state(self, run: RunModel, task: TaskModel) -> WorkflowState:
        return {
            "run_id": run.id,
            "task_id": task.id,
            "title": task.title,
            "description": task.description or task.request_text,
            "workspace_path": task.workspace_path or "",
            "task_type": task.task_type or "",
            "constraints": task.constraints,
            "target_files": task.target_files,
            "stage": run.current_stage,
            "status": run.status,
            "current_step": "initialized",
            "artifacts": [],
            "errors": [],
            "retry_count": run.retry_count,
            "error_message": run.error_message or "",
        }

    def _build_state_for_stage(self, run: RunModel, stage: str) -> WorkflowState:
        return {
            "run_id": run.id,
            "task_id": run.task_id,
            "stage": self._normalize_enum(stage),
            "status": self._normalize_enum(run.status),
            "retry_count": run.retry_count,
            "error_message": run.error_message or "",
        }

    def _record_state_snapshot(
        self,
        session,
        run: RunModel,
        state: WorkflowState,
        current_step: str,
        payload: dict[str, object],
    ) -> None:
        snapshot_state = dict(state)
        snapshot_state["stage"] = self._normalize_enum(run.current_stage)
        snapshot_state["status"] = self._normalize_enum(run.status)
        snapshot_state["current_step"] = current_step
        snapshot_state["retry_count"] = run.retry_count
        session.add(
            RunStateSnapshotModel(
                run_id=run.id,
                stage=self._normalize_enum(run.current_stage),
                status=self._normalize_enum(run.status),
                retry_count=run.retry_count,
                payload_json=json.dumps(
                    {
                        "state": snapshot_state,
                        "payload": payload,
                    },
                    indent=2,
                ),
            )
        )

    def _normalize_enum(self, value: str | StringEnum) -> str:
        if isinstance(value, StringEnum):
            return value.value
        return str(value)


_service: Optional[OrchestrationService] = None


def get_orchestration_service() -> OrchestrationService:
    global _service
    if _service is None:
        _service = OrchestrationService()
    return _service


def reset_orchestration_service() -> None:
    global _service
    if _service is not None:
        _service.stop()
    _service = None
