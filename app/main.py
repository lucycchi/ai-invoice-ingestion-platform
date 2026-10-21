"""Creates the FastAPI app: database, folders and routes."""

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.clients.claude import ClaudeClient
from app.clients.reference_api import ReferenceClient
from app.config import Settings
from app.db import make_engine, session_factory
from app.models import Base
from app.status import recover_interrupted
from app.web.confirm import router as confirm_router
from app.web.cross_site import add_host_guards
from app.web.finalize import router as finalize_router
from app.web.review import router as review_router
from app.web.routes import router, templates
from app.web.upload_limit import UploadSizeLimit


def create_app(settings: Settings, claude=None, reference=None) -> FastAPI:
    """Build the app. Tests pass stand-ins for the Claude and reference API clients."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "uploads").mkdir(exist_ok=True)
        engine = make_engine(settings.data_dir / "app.db")
        Base.metadata.create_all(engine)
        app.state.settings = settings
        app.state.sessions = session_factory(engine)
        with app.state.sessions() as session:
            recover_interrupted(session)
            session.commit()
        app.state.claude = claude or ClaudeClient(
            settings.anthropic_api_key.get_secret_value(), settings.anthropic_model
        )
        app.state.reference = reference or ReferenceClient(settings.reference_api_url)
        yield
        engine.dispose()

    app = FastAPI(title="AI Invoice Ingestion Platform", lifespan=lifespan)

    add_host_guards(app, settings.allowed_hosts)
    app.add_middleware(UploadSizeLimit)

    @app.exception_handler(HTTPException)
    async def not_found_page(request: Request, exc: HTTPException):
        """A page, not JSON, when someone opens an invoice or page that doesn't exist."""
        if exc.status_code != 404 or request.url.path.endswith(".json"):  # the export answers in JSON
            return await http_exception_handler(request, exc)
        message = exc.detail if exc.detail != "Not Found" else "There's no page at this address."
        return templates.TemplateResponse(request, "not_found.html", {"message": message}, status_code=404)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
    app.include_router(router)
    app.include_router(confirm_router)
    app.include_router(review_router)
    app.include_router(finalize_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
