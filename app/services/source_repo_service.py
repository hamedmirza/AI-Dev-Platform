from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.db.models import SavedSourceRepoModel
from app.schemas.source_repo import (
    SavedSourceRepoResponse,
    SourceRepoValidationResponse,
)
from app.services.source_repo_policy import (
    repo_key_for_source_spec,
    validate_source_repo_spec,
)
from app.tools.git_tools import current_head_sha, validate_git_repository


def validate_source_repo_for_operator(source_repo: str) -> SourceRepoValidationResponse:
    spec = source_repo.strip()
    resolved = validate_source_repo_spec(spec, get_settings())
    label = _default_label(spec)
    if resolved.kind == "local" and resolved.local_path is not None:
        summary = validate_git_repository(resolved.local_path)
        raw_remotes = summary.get("remotes")
        remotes_list = (
            [str(x) for x in raw_remotes] if isinstance(raw_remotes, list) else []
        )
        return SourceRepoValidationResponse(
            source_repo_spec=spec,
            kind="local",
            label=label,
            valid=True,
            branch=str(summary["branch"]),
            head_sha=current_head_sha(resolved.local_path),
            remotes=remotes_list,
            dirty=bool(summary["dirty"]),
        )
    return SourceRepoValidationResponse(
        source_repo_spec=spec,
        kind="remote",
        label=label,
        valid=True,
    )


def list_saved_source_repos(session: Session) -> list[SavedSourceRepoResponse]:
    rows = session.scalars(
        select(SavedSourceRepoModel)
        .where(SavedSourceRepoModel.status == "active")
        .order_by(SavedSourceRepoModel.updated_at.desc(), SavedSourceRepoModel.created_at.desc())
    ).all()
    return [_to_saved_response(row) for row in rows]


def save_source_repo(
    session: Session,
    source_repo: str,
    label: Optional[str],
) -> SavedSourceRepoResponse:
    validation = validate_source_repo_for_operator(source_repo)
    repo_key = repo_key_for_source_spec(validation.source_repo_spec)
    row = session.scalars(
        select(SavedSourceRepoModel).where(SavedSourceRepoModel.repo_key == repo_key)
    ).first()
    if row is None:
        row = SavedSourceRepoModel(
            label=(label or validation.label).strip() or validation.label,
            source_repo_spec=validation.source_repo_spec,
            repo_key=repo_key,
            kind=validation.kind,
        )
        session.add(row)
    else:
        row.label = (label or row.label or validation.label).strip() or validation.label
        row.source_repo_spec = validation.source_repo_spec
        row.kind = validation.kind
        row.status = "active"
    session.commit()
    session.refresh(row)
    return _to_saved_response(row)


def delete_saved_source_repo(session: Session, repo_id: str) -> None:
    row = session.get(SavedSourceRepoModel, repo_id)
    if row is None or row.status != "active":
        raise ValueError("Saved source repo not found.")
    row.status = "archived"
    session.commit()


def _to_saved_response(row: SavedSourceRepoModel) -> SavedSourceRepoResponse:
    try:
        validation = validate_source_repo_for_operator(row.source_repo_spec)
    except ConfigurationError:
        validation = SourceRepoValidationResponse(
            source_repo_spec=row.source_repo_spec,
            kind=row.kind,
            label=row.label,
            valid=False,
        )
    return SavedSourceRepoResponse(
        id=row.id,
        repo_key=row.repo_key,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source_repo_spec=row.source_repo_spec,
        kind=row.kind,
        label=row.label,
        valid=validation.valid,
        branch=validation.branch,
        head_sha=validation.head_sha,
        remotes=validation.remotes,
        dirty=validation.dirty,
    )


def _default_label(source_repo: str) -> str:
    spec = source_repo.rstrip("/")
    if spec.startswith(("https://", "http://", "git@", "ssh://")):
        tail = spec.rsplit("/", 1)[-1]
        return tail.removesuffix(".git") or spec
    return Path(spec).name or spec
