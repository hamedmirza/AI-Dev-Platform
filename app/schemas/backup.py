from pydantic import BaseModel


class BackupResponse(BaseModel):
    backup_path: str
    manifest_path: str
    database_included: bool
    settings_included: bool


class RestoreRehearsalResponse(BaseModel):
    rehearsal_path: str
    database_restored: bool
    manifest_loaded: bool
    cleanup_required: bool
