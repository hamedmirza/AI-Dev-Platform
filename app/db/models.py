
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    runs: Mapped[list["RunModel"]] = relationship(back_populates="task")

    @property
    def constraints(self) -> list[str]:
        return _decode_json_list(self.constraints_json)

    @property
    def target_files(self) -> list[str]:
        return _decode_json_list(self.target_files_json)


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


def _decode_json_list(raw_value: str) -> list[str]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]
