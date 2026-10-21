"""Running claimed work in the background, with a catch-all so an invoice never stays stuck."""

import logging

from app.logs import log_error
from app.status import fail

log = logging.getLogger(__name__)
MISSING_FILE = "The uploaded file is missing; please upload it again"


def run_guarded(session_factory, invoice_id: int, job) -> None:
    """Run `job`; any error it doesn't handle itself moves the invoice to its failure status."""
    try:
        job()
    except FileNotFoundError as err:
        log_error(log, "Stored file missing", invoice_id, err)
        _fail(session_factory, invoice_id, MISSING_FILE)
    except Exception as err:
        # Only the error's type, in the log and on the page: its text could hold invoice content.
        log_error(log, "Unexpected error in background work", invoice_id, err)
        _fail(session_factory, invoice_id, f"Unexpected error ({type(err).__name__}); the app log records where it happened")


def _fail(session_factory, invoice_id: int, reason: str) -> None:
    with session_factory() as session:
        fail(session, invoice_id, reason)
        session.commit()


def start(background_tasks, app, invoice_id: int, step) -> None:
    """Queue `step(app, invoice_id)` to run after the response is sent."""
    background_tasks.add_task(run_guarded, app.state.sessions, invoice_id, lambda: step(app, invoice_id))
