
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.config import require_api_token
from app.db.session import get_db
from app.services.artifact_service import list_artifacts
from app.services.run_service import get_run, get_run_history

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", dependencies=[Depends(require_api_token)])
def fetch_run(run_id: str, session: Session = Depends(get_db)):
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/runs/{run_id}/history", dependencies=[Depends(require_api_token)])
def fetch_run_history(run_id: str, session: Session = Depends(get_db)):
    return get_run_history(session, run_id)


@router.get("/runs/{run_id}/artifacts", dependencies=[Depends(require_api_token)])
def fetch_run_artifacts(run_id: str, session: Session = Depends(get_db)):
    return list_artifacts(session, run_id)
