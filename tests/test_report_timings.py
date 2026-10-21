from app.db import make_engine, session_factory
from app.models import Base, Invoice, Run
from app.report_timings import COLUMNS, render_table, timing_rows


def _setup(tmp_path, uploads):
    engine = make_engine(tmp_path / "app.db")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    with sessions() as s:
        for n, (name, uploaded_at) in enumerate(uploads, start=1):
            s.add(Invoice(id=n, status="in_review", original_filename=name, stored_path=f"{n}.pdf",
                          media_type="application/pdf", uploaded_at=uploaded_at))
            s.add(Run(invoice_id=n, step="extraction", started_at=uploaded_at,
                      stored_at=uploaded_at.replace(":00.000Z", ":14.000Z"), claude_requests=1,
                      input_tokens=5933, output_tokens=1373, outcome="succeeded"))
            s.add(Run(invoice_id=n, step="matching", started_at="2026-10-21T10:01:00.000Z",
                      stored_at="2026-10-21T10:01:08.400Z", shown_at="2026-10-21T10:01:09.400Z",
                      claude_requests=5, input_tokens=1550, output_tokens=1620, cache_read_tokens=18632,
                      cache_applied=True, outcome="succeeded"))
        s.commit()
    return sessions


def test_repeat_means_within_five_minutes(tmp_path):
    sessions = _setup(tmp_path, [
        ("large-invoice.pdf", "2026-10-21T10:00:00.000Z"),
        ("large-invoice.pdf", "2026-10-21T10:03:00.000Z"),
        ("large-invoice.pdf", "2026-10-21T10:13:00.000Z"),
    ])
    with sessions() as s:
        rows = [r for r in timing_rows(s) if r["step"] == "matching"]
    assert [r["run"] for r in rows] == ["first", "repeat", "first"]


def test_table_columns_and_values(tmp_path):
    sessions = _setup(tmp_path, [("large-invoice.pdf", "2026-10-21T10:00:00.000Z")])
    with sessions() as s:
        table = render_table(timing_rows(s))
    header = table.splitlines()[0]
    assert header == "| " + " | ".join(COLUMNS) + " |"
    assert COLUMNS == ["Invoice file", "Step", "Run", "On-screen seconds", "Stored seconds", "Claude requests",
                       "Input tokens", "Output tokens", "Cache-read tokens", "Cache applied"]
    assert "| large-invoice.pdf | matching | first | 9.4 | 8.4 | 5 | 1550 | 1620 | 18632 | yes |" in table
    assert "| large-invoice.pdf | extraction | first | — | 14.0 | 1 | 5933 | 1373 | 0 | no |" in table
