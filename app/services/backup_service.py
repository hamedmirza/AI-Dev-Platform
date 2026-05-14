import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core.exceptions import ConfigurationError
from app.core.settings import get_settings
from app.schemas.backup import BackupResponse, RestoreRehearsalResponse


def _sqlite_file_path() -> Path:
    settings = get_settings()
    if not settings.db_url.startswith("sqlite:///"):
        raise ConfigurationError("Backup service only supports sqlite database URLs.")
    return Path(settings.db_url.removeprefix("sqlite:///")).resolve()


def create_backup() -> BackupResponse:
    settings = get_settings()
    backup_root = settings.backup_root_path
    backup_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target_dir = backup_root / f"backup-{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=False)

    db_path = _sqlite_file_path()
    copied_db = target_dir / db_path.name
    _backup_sqlite_database(db_path, copied_db)

    manifest = {
        "db_url": settings.db_url,
        "workspace_root": str(settings.workspace_root_path),
        "source_repo_path": (
            str(settings.source_repo_path_resolved) if settings.source_repo_path_resolved else None
        ),
        "created_at": timestamp,
    }
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return BackupResponse(
        backup_path=str(copied_db),
        manifest_path=str(manifest_path),
        database_included=True,
        settings_included=True,
    )


def _backup_sqlite_database(source_db: Path, target_db: Path) -> None:
    """Create a consistent SQLite backup even while writes are active."""
    settings = get_settings()
    if settings.db_url.startswith("sqlite:///"):
        # Use sqlite online backup API against the live DB.
        src = sqlite3.connect(str(source_db), timeout=30)
        dst = sqlite3.connect(str(target_db), timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return
    shutil.copy2(source_db, target_db)


def rehearse_restore(manifest_path: Path) -> RestoreRehearsalResponse:
    if not manifest_path.exists():
        raise ConfigurationError(f"Backup manifest does not exist: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not str(manifest["db_url"]).startswith("sqlite:///"):
        raise ConfigurationError("Restore rehearsal only supports sqlite database URLs.")

    source_db_name = Path(str(manifest["db_url"]).removeprefix("sqlite:///")).name
    source_db_path = manifest_path.parent / source_db_name
    if not source_db_path.exists():
        raise ConfigurationError(f"Backup database file is missing: {source_db_path}")

    rehearsal_dir = manifest_path.parent / "restore-rehearsal"
    rehearsal_dir.mkdir(parents=True, exist_ok=True)
    rehearsal_db = rehearsal_dir / source_db_name
    shutil.copy2(source_db_path, rehearsal_db)

    return RestoreRehearsalResponse(
        rehearsal_path=str(rehearsal_dir),
        database_restored=True,
        manifest_loaded=True,
        cleanup_required=True,
    )
