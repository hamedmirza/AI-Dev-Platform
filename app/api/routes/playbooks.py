from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.db.session import get_db
from app.schemas.playbook import (
    PlaybookCreate,
    PlaybookHumanConfirm,
    PlaybookHumanVeto,
    PlaybookRow,
)
from app.services.playbook_service import (
    create_playbook_draft,
    human_confirm_playbook,
    human_veto_playbook,
    list_pending_human,
    run_supervisor_on_draft,
)

router = APIRouter(tags=["playbooks"])


@router.get("/playbooks/pending", dependencies=[Depends(require_api_token)])
def playbooks_pending(
    repo_key: Optional[str] = Query(default=None),
    session: Session = Depends(get_db),
) -> list[PlaybookRow]:
    rows = list_pending_human(session, repo_key=repo_key)
    return [PlaybookRow.model_validate(r) for r in rows]


@router.post(
    "/playbooks",
    dependencies=[Depends(require_api_token)],
    status_code=status.HTTP_201_CREATED,
)
def playbooks_create(payload: PlaybookCreate, session: Session = Depends(get_db)) -> PlaybookRow:
    row = create_playbook_draft(
        session,
        repo_key=payload.repo_key,
        role=payload.role,
        content=payload.content,
        proposed_by_run_id=payload.proposed_by_run_id,
    )
    session.commit()
    session.refresh(row)
    return PlaybookRow.model_validate(row)


@router.post("/playbooks/{row_id}/supervisor", dependencies=[Depends(require_api_token)])
def playbooks_supervisor(row_id: int, session: Session = Depends(get_db)) -> PlaybookRow:
    try:
        row = run_supervisor_on_draft(session, row_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.refresh(row)
    return PlaybookRow.model_validate(row)


@router.post("/playbooks/{row_id}/human-confirm", dependencies=[Depends(require_api_token)])
def playbooks_human_confirm(
    row_id: int,
    payload: PlaybookHumanConfirm,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        human_confirm_playbook(session, row_id, payload.actor, payload.notes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/playbooks/{row_id}/human-veto", dependencies=[Depends(require_api_token)])
def playbooks_human_veto(
    row_id: int,
    payload: PlaybookHumanVeto,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        human_veto_playbook(session, row_id, payload.actor, payload.reason)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
