"""Logging an unexpected error without its text, which could hold content read from an invoice."""

import traceback


def log_error(log, message: str, invoice_id: int, err: BaseException) -> None:
    """Log the error's type and where it happened (file, line, function and code line), never its message."""
    where = "".join(traceback.format_tb(err.__traceback__))
    log.error("%s for invoice %s: %s\n%s", message, invoice_id, type(err).__name__, where)
