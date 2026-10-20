"""Creates the FastAPI app: database, folders and routes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.db import make_engine, session_factory
from app.models import Base
from app.status import recover_interrupted


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
        app.state.claude = claude
        app.state.reference = reference
        yield
        engine.dispose()

    app = FastAPI(title="AI Invoice Ingestion Platform", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
