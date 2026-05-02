"""Supervised per-role playbooks (Part J)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RunStage
from app.core.exceptions import ConfigurationError
from app.core.settings import Settings, get_settings
from app.db.models import RolePlaybookModel
from app.providers.registry import resolve_provider


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_FORBIDDEN = re.compile(
    r"(?i)(api[_-]?key|password|secret|bearer\s|eval\(|exec\(|disable\s+guard|rm\s+-rf)",
)


def _sanitize_playbook_text(raw: str, settings: Settings) -> str:
    text = raw.strip()[: settings.playbook_char_limit]
    if _FORBIDDEN.search(text):
        raise ConfigurationError("Playbook content matched forbidden patterns.")
    return text


def load_active_playbook_overlay(session: Session, repo_key: str, stage: RunStage) -> str:
    row = session.scalars(
        select(RolePlaybookModel)
        .where(
            RolePlaybookModel.repo_key == repo_key,
            RolePlaybookModel.role == stage.value,
            RolePlaybookModel.status == "active",
        )
        .order_by(RolePlaybookModel.version.desc(), RolePlaybookModel.id.desc())
        .limit(1)
    ).first()
    if row is None or not row.content.strip():
        return ""
    cap = get_settings().playbook_char_limit
    return row.content.strip()[:cap]


def create_playbook_draft(
    session: Session,
    *,
    repo_key: str,
    role: str,
    content: str,
    proposed_by_run_id: Optional[str] = None,
) -> RolePlaybookModel:
    settings = get_settings()
    body = _sanitize_playbook_text(content, settings)
    row = RolePlaybookModel(
        repo_key=repo_key,
        role=role,
        content=body,
        status="draft",
        proposed_by_run_id=proposed_by_run_id,
        version=1,
    )
    session.add(row)
    session.flush()
    return row


def run_supervisor_on_draft(session: Session, row_id: int) -> RolePlaybookModel:
    settings = get_settings()
    row = session.get(RolePlaybookModel, row_id)
    if row is None:
        raise ConfigurationError("Playbook row not found.")
    if row.status != "draft":
        raise ConfigurationError("Playbook is not in draft state.")

    if not settings.playbook_supervisor_enabled:
        row.status = "pending_human"
        row.supervisor_merged_content = row.content
        row.supervisor_decision = "skipped"
        row.supervisor_rationale = "Supervisor disabled by configuration."
        row.supervisor_run_at = utc_now()
        session.commit()
        return row

    active = session.scalars(
        select(RolePlaybookModel)
        .where(
            RolePlaybookModel.repo_key == row.repo_key,
            RolePlaybookModel.role == row.role,
            RolePlaybookModel.status == "active",
        )
        .order_by(RolePlaybookModel.version.desc())
        .limit(1)
    ).first()
    prior = active.content if active else ""

    prompt_path = Path(settings.playbook_supervisor_system_prompt_path)
    system = (
        prompt_path.read_text(encoding="utf-8").strip()
        if prompt_path.exists()
        else "You review playbook overlay text for safety and clarity. Return JSON only."
    )
    user = json.dumps(
        {
            "proposed": row.content,
            "current_active": prior,
            "instructions": (
                'Return JSON: {"decision":"approve"|"reject"|"revise",'
                '"merged_content":"...", "rationale":"..."}. merged_content must be safe markdown.'
            ),
        }
    )
    supervisor_model = settings.lmstudio_model_supervisor or settings.lmstudio_model
    provider = resolve_provider(None, supervisor_model)
    raw = provider.structured_completion(system, user)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Supervisor returned invalid JSON: {exc}") from exc
    decision = str(payload.get("decision", "")).lower()
    merged = str(payload.get("merged_content", "") or "").strip()
    rationale = str(payload.get("rationale", "") or "").strip()

    row.supervisor_decision = decision
    row.supervisor_rationale = rationale
    row.supervisor_model_id = supervisor_model
    row.supervisor_run_at = utc_now()

    if decision == "reject":
        row.status = "supervisor_rejected"
        row.rejection_reason = rationale or "Rejected by supervisor."
    elif decision in {"approve", "revise"}:
        row.supervisor_merged_content = _sanitize_playbook_text(merged or row.content, settings)
        row.status = "pending_human"
    else:
        row.status = "supervisor_rejected"
        row.rejection_reason = "Supervisor returned an invalid decision."

    session.commit()
    return row


def human_confirm_playbook(
    session: Session,
    row_id: int,
    actor: str,
    notes: Optional[str] = None,
) -> None:
    settings = get_settings()
    row = session.get(RolePlaybookModel, row_id)
    if row is None:
        raise ConfigurationError("Playbook row not found.")
    if row.status != "pending_human":
        raise ConfigurationError("Playbook is not awaiting human confirmation.")
    final_text = (row.supervisor_merged_content or row.content).strip()
    final_text = _sanitize_playbook_text(final_text, settings)

    for prev in session.scalars(
        select(RolePlaybookModel).where(
            RolePlaybookModel.repo_key == row.repo_key,
            RolePlaybookModel.role == row.role,
            RolePlaybookModel.status == "active",
        )
    ).all():
        prev.status = "archived"

    row.content = final_text
    row.status = "active"
    row.human_decision = "confirm"
    row.human_actor = actor
    row.human_acted_at = utc_now()
    row.human_notes = notes
    row.version = (row.version or 1) + 1
    session.commit()


def human_veto_playbook(session: Session, row_id: int, actor: str, reason: str) -> None:
    row = session.get(RolePlaybookModel, row_id)
    if row is None:
        raise ConfigurationError("Playbook row not found.")
    if row.status != "pending_human":
        raise ConfigurationError("Playbook is not awaiting human confirmation.")
    row.status = "human_vetoed"
    row.human_decision = "veto"
    row.human_actor = actor
    row.human_acted_at = utc_now()
    row.human_notes = reason
    row.rejection_reason = reason
    session.commit()


def list_pending_human(session: Session, repo_key: Optional[str] = None) -> list[RolePlaybookModel]:
    q = select(RolePlaybookModel).where(RolePlaybookModel.status == "pending_human")
    if repo_key:
        q = q.where(RolePlaybookModel.repo_key == repo_key)
    q = q.order_by(RolePlaybookModel.id.desc())
    return list(session.scalars(q).all())
