
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=4)
def _get_engine(db_url: str):
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args, future=True)


@lru_cache(maxsize=4)
def _get_session_factory(db_url: str):
    return sessionmaker(bind=_get_engine(db_url), expire_on_commit=False, class_=Session)


def get_engine():
    return _get_engine(get_settings().db_url)


def get_session_factory():
    return _get_session_factory(get_settings().db_url)


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from app.db.models import (  # noqa: F401
        ArtifactModel,
        RunEventModel,
        RunModel,
        RunStateSnapshotModel,
        TaskModel,
    )

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations(engine)


def _apply_lightweight_migrations(engine) -> None:
    inspector = inspect(engine)

    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    run_columns = {column["name"] for column in inspector.get_columns("runs")}

    task_additions = {
        "description": "TEXT",
        "workspace_path": "TEXT",
        "task_type": "VARCHAR(128)",
        "constraints_json": "TEXT DEFAULT '[]' NOT NULL",
        "target_files_json": "TEXT DEFAULT '[]' NOT NULL",
        "provider_override": "VARCHAR(128)",
        "model_override": "VARCHAR(255)",
    }
    run_additions = {
        "request_id": "VARCHAR(64)",
        "retry_count": "INTEGER DEFAULT 0 NOT NULL",
    }

    with engine.begin() as connection:
        for column_name, ddl in task_additions.items():
            if column_name not in task_columns:
                connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {column_name} {ddl}"))
        for column_name, ddl in run_additions.items():
            if column_name not in run_columns:
                connection.execute(text(f"ALTER TABLE runs ADD COLUMN {column_name} {ddl}"))
