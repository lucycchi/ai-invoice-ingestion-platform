"""Print a Markdown table of every reading and matching run, for the README's timing report.

Run inside the app's container:  docker compose exec app python -m app.report_timings
A run is a "repeat" when the same file was uploaded within five minutes of its "first" run (Claude's
default cache lifetime); the next upload after that window starts a new "first". Files are told apart by
name. "First group warmed the cache" says whether the first group of lines was sent alone to write
Claude's cache; the cache-read tokens column shows whether the cache was actually read.
"""

from datetime import datetime, timedelta

from app.clock import seconds_between
from app.models import Invoice, Run

COLUMNS = ["Invoice file", "Step", "Run", "On-screen seconds", "Stored seconds", "Claude requests",
           "Input tokens", "Output tokens", "Cache-read tokens", "First group warmed the cache"]
REPEAT_WINDOW = timedelta(minutes=5)


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def timing_rows(session) -> list[dict]:
    invoices = session.query(Invoice).order_by(Invoice.uploaded_at).all()
    first_run: dict[str, datetime] = {}
    kind = {}
    for invoice in invoices:
        uploaded = _time(invoice.uploaded_at)
        first = first_run.get(invoice.original_filename)
        if first and uploaded - first <= REPEAT_WINDOW:
            kind[invoice.id] = "repeat"
        else:
            kind[invoice.id] = "first"
            first_run[invoice.original_filename] = uploaded
    names = {invoice.id: invoice.original_filename for invoice in invoices}
    rows = []
    for run in session.query(Run).order_by(Run.invoice_id, Run.id):
        rows.append({
            "file": names[run.invoice_id],
            "step": run.step,
            "run": kind[run.invoice_id],
            "shown": seconds_between(run.started_at, run.shown_at),
            "stored": seconds_between(run.started_at, run.stored_at),
            "requests": run.claude_requests,
            "input": run.input_tokens,
            "output": run.output_tokens,
            "cache_read": run.cache_read_tokens,
            "cache_applied": "yes" if run.cache_applied else "no",
            "outcome": run.outcome,
        })
    return rows


def render_table(rows: list[dict]) -> str:
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in rows:
        cells = [r["file"], r["step"], r["run"], _seconds(r["shown"]), _seconds(r["stored"]), r["requests"],
                 r["input"], r["output"], r["cache_read"], r["cache_applied"]]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(lines)


def main() -> None:
    from app.config import Settings
    from app.db import make_engine, session_factory

    settings = Settings()
    with session_factory(make_engine(settings.data_dir / "app.db"))() as session:
        print(render_table(timing_rows(session)))


if __name__ == "__main__":
    main()
