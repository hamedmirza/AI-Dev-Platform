
import json
import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from pydantic import BaseModel

from app.core.enums import ArtifactType, ProviderStatus, RunStage, RunStatus
from app.core.exceptions import ProviderError
from app.core.settings import get_settings
from app.db.models import ArtifactModel, RunEventModel, RunModel, TaskModel
from app.db.session import get_session_factory
from app.providers.registry import get_provider
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
        provider_health = get_provider().healthcheck()
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
            finally:
                self._queue.task_done()

    def _process_run(self, run_id: str) -> None:
        session = get_session_factory()()
        try:
            run = session.get(RunModel, run_id)
            if run is None:
                return

            task = session.get(TaskModel, run.task_id)
            if task is None:
                run.status = RunStatus.FAILED
                run.error_message = "Task record is missing."
                session.commit()
                return

            provider = get_provider()
            workspace_path = create_run_workspace(run.id)
            run.status = RunStatus.RUNNING
            self._add_event(
                session,
                run.id,
                "run_started",
                f"Worker started the run in {workspace_path}.",
            )
            session.commit()

            planner_stage = self._stage_by_name(RunStage.PLANNER)
            architect_stage = self._stage_by_name(RunStage.ARCHITECT)
            coder_stage = self._stage_by_name(RunStage.CODER)
            reviewer_stage = self._stage_by_name(RunStage.REVIEWER)
            tester_stage = self._stage_by_name(RunStage.TESTER)

            planner_model = self._run_stage(session, run, provider, planner_stage, task.request_text)
            architect_model = self._run_stage(session, run, provider, architect_stage, task.request_text)

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
                self._run_stage(session, run, provider, coder_stage, coder_prompt)

                review_prompt = self._build_review_request(task.request_text, retry_feedback)
                review_model = cast(
                    ReviewResponse,
                    self._run_stage(session, run, provider, reviewer_stage, review_prompt),
                )
                if not review_model.approved:
                    review_retries += 1
                    total_retries += 1
                    retry_feedback = [review_model.summary, *review_model.issues]
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
                    self._add_event(
                        session,
                        run.id,
                        "review_rejected",
                        "Reviewer rejected the current proposal; retrying coder stage.",
                        review_model.model_dump_json(),
                    )
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue

                test_prompt = self._build_test_request(task.request_text, retry_feedback)
                test_model = cast(
                    TestResultResponse,
                    self._run_stage(session, run, provider, tester_stage, test_prompt),
                )
                if not test_model.passed:
                    test_retries += 1
                    total_retries += 1
                    retry_feedback = [test_model.summary, *test_model.failures]
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
                    self._add_event(
                        session,
                        run.id,
                        "tests_failed",
                        "Validation stage reported failures; retrying coder stage.",
                        test_model.model_dump_json(),
                    )
                    session.commit()
                    run.status = RunStatus.RUNNING
                    continue

                break

            run.status = RunStatus.AWAITING_APPROVAL
            run.current_stage = RunStage.APPROVAL
            run.error_message = None
            self._add_event(
                session,
                run.id,
                "awaiting_approval",
                "Run is awaiting operator approval before any git-side effects.",
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
    ) -> BaseModel:
        run.current_stage = stage.stage
        self._add_event(session, run.id, f"{stage.stage}_started", f"Started {stage.stage} stage.")
        session.commit()

        model = self._invoke_stage(provider, stage, request_text)
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
        return "\n".join([request_text, "Focus review on prior issues being resolved:", *retry_feedback])

    def _build_test_request(self, request_text: str, retry_feedback: list[str]) -> str:
        if not retry_feedback:
            return request_text
        return "\n".join(
            [request_text, "Focus validation on prior failures being resolved:", *retry_feedback]
        )

    def _invoke_stage(self, provider, stage: StageDefinition, request_text: str) -> BaseModel:
        prompt_path = Path(stage.system_prompt_path)
        system_prompt = prompt_path.read_text(encoding="utf-8").strip()
        raw = provider.invoke_json(
            system_prompt,
            stage.user_prompt_template.format(request_text=request_text),
        )
        payload = json.loads(raw)
        return stage.schema.model_validate(payload)

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
