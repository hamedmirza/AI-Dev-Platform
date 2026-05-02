
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.routes.backups import router as backups_router
from app.api.routes.config import router as config_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import router as runs_router
from app.api.routes.tasks import router as tasks_router
from app.core.logging import configure_logging
from app.core.request_context import set_request_id, set_run_id
from app.core.settings import get_settings
from app.db.session import init_db
from app.services.orchestration_service import get_orchestration_service
from app.ui.routes import router as ui_router

logger = logging.getLogger(__name__)


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

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        set_request_id(request_id)
        set_run_id(None)
        logger.info("request started %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
        finally:
            logger.info("request finished %s %s", request.method, request.url.path)
            set_request_id(None)
            set_run_id(None)

        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router, prefix="/api")
    app.include_router(backups_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(ui_router)
    ui_assets = Path(__file__).resolve().parents[1] / "ui" / "static" / "assets"
    if ui_assets.exists():
        app.mount("/ui/assets", StaticFiles(directory=ui_assets), name="ui-assets")
    return app


app = create_app()
