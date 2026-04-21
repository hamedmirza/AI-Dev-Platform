
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.backups import router as backups_router
from app.api.routes.config import router as config_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import router as runs_router
from app.api.routes.tasks import router as tasks_router
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.db.session import init_db
from app.services.orchestration_service import get_orchestration_service
from app.ui.routes import router as ui_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    orchestration = get_orchestration_service()
    orchestration.start()
    try:
        yield
    finally:
        orchestration.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Dev Platform", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router, prefix="/api")
    app.include_router(backups_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(ui_router)
    return app


app = create_app()
