"""Running claimed work in the background, with a catch-all so an invoice never stays stuck."""

import logging

from app.status import fail

log = logging.getLogger(__name__)
MISSING_FILE = "The uploaded file is missing; please upload it again"


def run_guarded(session_factory, invoice_id: int, job) -> None:
    """Run `job`; any error it doesn't handle itself moves the invoice to its failure status."""
    try:
        job()
    except FileNotFoundError:
        log.exception("Stored file missing for invoice %s", invoice_id)
        _fail(session_factory, invoice_id, MISSING_FILE)
    except Exception as err:
        log.exception("Unexpected error in background work for invoice %s", invoice_id)
        # Only the error's type: its text could hold invoice content.
        _fail(session_factory, invoice_id, f"Unexpected error ({type(err).__name__}); details are in the app log")


def _fail(session_factory, invoice_id: int, reason: str) -> None:
    with session_factory() as session:
        fail(session, invoice_id, reason)
        session.commit()


def start(background_tasks, app, invoice_id: int, step) -> None:
    """Queue `step(app, invoice_id)` to run after the response is sent."""
    background_tasks.add_task(run_guarded, app.state.sessions, invoice_id, lambda: step(app, invoice_id))
