
import json
import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from pydantic import BaseModel

from app.core.enums import ArtifactType, RunStage, RunStatus
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

logger = logging.getLogger(__name__)


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
            run.status = RunStatus.RUNNING
            session.add(
                RunEventModel(
                    run_id=run.id,
                    event_type="run_started",
                    message="Worker started the run.",
                )
            )
            session.commit()

            for stage in STAGES:
                run.current_stage = stage.stage
                session.add(
                    RunEventModel(
                        run_id=run.id,
                        event_type=f"{stage.stage}_started",
                        message=f"Started {stage.stage} stage.",
                    )
                )
                session.commit()

                model = self._invoke_stage(provider, stage, task.request_text)
                artifact = self._make_artifact(
                    run.id,
                    stage.artifact_type,
                    stage.artifact_title,
                    model,
                )
                session.add(artifact)

                if stage.stage == RunStage.REVIEWER:
                    review_model = cast(ReviewResponse, model)
                    if not review_model.approved:
                        run.status = RunStatus.NEEDS_REVISION
                        run.error_message = "Reviewer requested changes."
                        session.add(
                            RunEventModel(
                                run_id=run.id,
                                event_type="review_rejected",
                                message="Reviewer rejected the current proposal.",
                                payload_json=review_model.model_dump_json(),
                            )
                        )
                        session.commit()
                        return

                if stage.stage == RunStage.TESTER:
                    test_model = cast(TestResultResponse, model)
                    if not test_model.passed:
                        run.status = RunStatus.NEEDS_REVISION
                        run.error_message = "Validation stage reported failures."
                        session.add(
                            RunEventModel(
                                run_id=run.id,
                                event_type="tests_failed",
                                message="Validation stage reported failures.",
                                payload_json=test_model.model_dump_json(),
                            )
                        )
                        session.commit()
                        return

                session.add(
                    RunEventModel(
                        run_id=run.id,
                        event_type=f"{stage.stage}_completed",
                        message=f"Completed {stage.stage} stage.",
                        payload_json=model.model_dump_json(),
                    )
                )
                session.commit()

            run.status = RunStatus.AWAITING_APPROVAL
            run.current_stage = RunStage.APPROVAL
            run.error_message = None
            session.add(
                RunEventModel(
                    run_id=run.id,
                    event_type="awaiting_approval",
                    message="Run is awaiting operator approval before any git-side effects.",
                )
            )
            session.commit()
        except ProviderError as exc:
            run = session.get(RunModel, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.current_stage = run.current_stage or RunStage.INTAKE
                run.error_message = str(exc)
                session.add(
                    RunEventModel(
                        run_id=run.id,
                        event_type="provider_failed",
                        message=str(exc),
                    )
                )
                session.commit()
        finally:
            session.close()

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
