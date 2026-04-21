from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.config import require_api_token
from app.core.exceptions import ConfigurationError
from app.schemas.backup import BackupResponse, RestoreRehearsalResponse
from app.services.backup_service import create_backup, rehearse_restore

router = APIRouter(tags=["backups"])


@router.post(
    "/backups/run",
    dependencies=[Depends(require_api_token)],
    response_model=BackupResponse,
)
def run_backup():
    try:
        return create_backup()
    except ConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/backups/restore-rehearsal",
    dependencies=[Depends(require_api_token)],
    response_model=RestoreRehearsalResponse,
)
def run_restore_rehearsal(manifest_path: str):
    try:
        return rehearse_restore(Path(manifest_path))
    except ConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
