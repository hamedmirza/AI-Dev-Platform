
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    request_text: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    constraints_json: Mapped[str] = mapped_column(Text, default="[]")
    target_files_json: Mapped[str] = mapped_column(Text, default="[]")
    provider_override: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model_override: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_repo_spec: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    use_scout: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_models_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    runs: Mapped[list["RunModel"]] = relationship(back_populates="task")

    @property
    def constraints(self) -> list[str]:
        return _decode_json_list(self.constraints_json)

    @property
    def target_files(self) -> list[str]:
        return _decode_json_list(self.target_files_json)


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    initial_requirements: Mapped[str] = mapped_column(Text)
    source_repo_spec: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repo_key: Mapped[str] = mapped_column(String(64), index=True, default="global")
    status: Mapped[str] = mapped_column(String(64), index=True, default="intake")
    app_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_stack_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_profile: Mapped[str] = mapped_column(String(128), default="python")
    readiness_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    messages: Mapped[list["ProjectMessageModel"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    questions: Mapped[list["ProjectQuestionModel"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    build_items: Mapped[list["ProjectBuildItemModel"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class SavedSourceRepoModel(Base):
    __tablename__ = "saved_source_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    label: Mapped[str] = mapped_column(String(255))
    source_repo_spec: Mapped[str] = mapped_column(Text)
    repo_key: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ProjectMessageModel(Base):
    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    message_type: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[ProjectModel] = relationship(back_populates="messages")


class ProjectQuestionModel(Base):
    __tablename__ = "project_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(String(64), default="text")
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), index=True, default="open")
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="questions")


class ProjectBuildItemModel(Base):
    __tablename__ = "project_build_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(64), default="task")
    status: Mapped[str] = mapped_column(String(64), index=True, default="draft")
    target_files_json: Mapped[str] = mapped_column(Text, default="[]")
    depends_on_json: Mapped[str] = mapped_column(Text, default="[]")
    assigned_role: Mapped[str] = mapped_column(String(64), default="coder")
    run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    project: Mapped[ProjectModel] = relationship(back_populates="build_items")

    @property
    def target_files(self) -> list[str]:
        return _decode_json_list(self.target_files_json)

    @property
    def depends_on(self) -> list[str]:
        return _decode_json_list(self.depends_on_json)


class RunModel(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    current_stage: Mapped[str] = mapped_column(String(64))
    provider_name: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    task: Mapped[TaskModel] = relationship(back_populates="runs")
    events: Mapped[list["RunEventModel"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["ArtifactModel"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    state_snapshots: Mapped[list["RunStateSnapshotModel"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class RunEventModel(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[RunModel] = relationship(back_populates="events")


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[RunModel] = relationship(back_populates="artifacts")


class RunStateSnapshotModel(Base):
    __tablename__ = "run_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[RunModel] = relationship(back_populates="state_snapshots")


class RepoLessonModel(Base):
    """Cross-run factual snippets for planner context (per repo_key scope)."""

    __tablename__ = "repo_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_key: Mapped[str] = mapped_column(String(64), index=True)
    body: Mapped[str] = mapped_column(Text)
    source_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RolePlaybookModel(Base):
    """Per-role supervised playbook overlay (Part J)."""

    __tablename__ = "role_playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    proposed_by_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    supervisor_decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    supervisor_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supervisor_merged_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supervisor_model_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supervisor_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    human_decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    human_actor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    human_acted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    human_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _decode_json_list(raw_value: str) -> list[str]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]
