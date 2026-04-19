
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
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
    from app.db.models import ArtifactModel, RunEventModel, RunModel, TaskModel  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
