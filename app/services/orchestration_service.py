
from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from pydantic import BaseModel

from app.core.enums import ArtifactType, ProviderStatus, RunStage, RunStatus, StringEnum
from app.core.exceptions import ProviderError
from app.core.request_context import set_request_id, set_run_id
from app.core.settings import get_settings
from app.db.models import ArtifactModel, RunEventModel, RunModel, RunStateSnapshotModel, TaskModel
from app.db.session import get_session_factory
from app.graph.state import WorkflowState
from app.providers.registry import get_provider, resolve_provider
from app.schemas.architecture import ArchitectureResponse
from app.schemas.code_change import CodeChangeResponse
from app.schemas.plan import PlanResponse
from app.schemas.review import ReviewResponse
from app.schemas.test_result import TestResultResponse
from app.services.repository_service import create_run_workspace

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
        stage=RunStage.CODER,
        artifact_type=ArtifactType.CODE_CHANGE,
        artifact_title="Proposed code change",
        schema=CodeChangeResponse,
        system_prompt_path="app/agents/prompts/coder.md",
        user_prompt_template=(
            "Return JSON with changed_files, implementation_notes, and "
            "requires_operator_approval for this task:\n\n{request_text}"
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
            "validation strategy for this task:\n\n{request_text}"
        ),
    ),
]


class OrchestrationService:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        settings = get_settings()
        settings.workspace_root_path.mkdir(parents=True, exist_ok=True)
        settings.backup_root_path.mkdir(parents=True, exist_ok=True)
        provider_health = get_provider().health_check()
        if provider_health.status == ProviderStatus.UNAVAILABLE:
            raise ProviderError(provider_health.detail)

        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="orchestration-worker",
            daemon=True,
        )
        self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)

    def enqueue_run(self, run_id: str) -> None:
        self._queue.put(run_id)

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
            set_run_id(run.id)
            set_request_id(run.request_id)

            task = session.get(TaskModel, run.task_id)
            if task is None:
                run.status = RunStatus.FAILED
                run.error_message = "Task record is missing."
                session.commit()
                return

            workflow_state = self._build_workflow_state(run, task)

            provider = resolve_provider(task.provider_override, task.model_override)
            workspace_path = create_run_workspace(run.id)
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

            planner_stage = self._stage_by_name(RunStage.PLANNER)
            architect_stage = self._stage_by_name(RunStage.ARCHITECT)
            coder_stage = self._stage_by_name(RunStage.CODER)
            reviewer_stage = self._stage_by_name(RunStage.REVIEWER)
            tester_stage = self._stage_by_name(RunStage.TESTER)

            planner_model = self._run_planner_with_guard(
                session=session,
                run=run,
                provider=provider,
                stage=planner_stage,
                request_text=task.request_text,
                workflow_state=workflow_state,
            )
            if planner_model is None:
                return
            workflow_state["planner_output"] = planner_model.model_dump_json()
            architect_model = cast(
                ArchitectureResponse,
                self._run_stage(session, run, provider, architect_stage, task.request_text),
            )
            workflow_state["architecture_output"] = architect_model.model_dump_json()

            review_retries = 0
            test_retries = 0
            total_retries = 0
            retry_feedback: list[str] = []

            while True:
                coder_prompt = self._build_coder_request(
                    task.request_text,
                    planner_model,
                    architect_model,
                    retry_feedback,
                )
                code_model = cast(
                    CodeChangeResponse,
                    self._run_stage(session, run, provider, coder_stage, coder_prompt),
                )
                workflow_state["code_output"] = code_model.model_dump_json()

                review_prompt = self._build_review_request(task.request_text, retry_feedback)
                review_model = cast(
                    ReviewResponse,
                    self._run_stage(session, run, provider, reviewer_stage, review_prompt),
                )
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
                    self._run_stage(session, run, provider, tester_stage, test_prompt),
                )
                workflow_state["test_output"] = test_model.model_dump_json()
                if not test_model.passed:
                    test_retries += 1
                    total_retries += 1
                    retry_feedback = [test_model.summary, *test_model.failures]
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

    def _run_stage(
        self,
        session,
        run: RunModel,
        provider,
        stage: StageDefinition,
        request_text: str,
        timeout_seconds: Optional[float] = None,
    ) -> BaseModel:
        run.current_stage = stage.stage
        self._add_event(session, run.id, f"{stage.stage}_started", f"Started {stage.stage} stage.")
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, stage.stage),
            current_step=f"{stage.stage}_started",
            payload={"stage": stage.stage},
        )
        session.commit()

        model = self._invoke_stage(provider, stage, request_text, timeout_seconds=timeout_seconds)
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
            f"{stage.stage}_completed",
            f"Completed {stage.stage} stage.",
            model.model_dump_json(),
        )
        self._record_state_snapshot(
            session,
            run,
            self._build_state_for_stage(run, stage.stage),
            current_step=f"{stage.stage}_completed",
            payload=model.model_dump(),
        )
        session.commit()
        return model

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
        planner_model: PlanResponse,
        architect_model: ArchitectureResponse,
        retry_feedback: list[str],
    ) -> str:
        sections = [
            request_text,
            "\nPlanner summary:",
            planner_model.model_dump_json(indent=2),
            "\nArchitecture plan:",
            architect_model.model_dump_json(indent=2),
        ]
        if retry_feedback:
            sections.extend(["\nRetry feedback:", *[f"- {item}" for item in retry_feedback]])
        return "\n".join(sections)

    def _build_review_request(self, request_text: str, retry_feedback: list[str]) -> str:
        if not retry_feedback:
            return request_text
        return "\n".join(
            [request_text, "Focus review on prior issues being resolved:", *retry_feedback]
        )

    def _build_test_request(self, request_text: str, retry_feedback: list[str]) -> str:
        if not retry_feedback:
            return request_text
        return "\n".join(
            [request_text, "Focus validation on prior failures being resolved:", *retry_feedback]
        )

    def _invoke_stage(
        self,
        provider,
        stage: StageDefinition,
        request_text: str,
        timeout_seconds: Optional[float] = None,
    ) -> BaseModel:
        prompt_path = Path(stage.system_prompt_path)
        system_prompt = prompt_path.read_text(encoding="utf-8").strip()
        user_prompt = stage.user_prompt_template.format(request_text=request_text)
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
            payload = json.loads(raw)
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
        payload = json.loads(raw)
        return stage.schema.model_validate(payload)

    def _run_planner_with_guard(
        self,
        session,
        run: RunModel,
        provider,
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
                        provider,
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
