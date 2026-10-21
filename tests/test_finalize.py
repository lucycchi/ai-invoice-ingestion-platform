import json
import threading
import time
from html import unescape

from app.models import Invoice, LineItem, LineMatch
from app.status import Status, locked_invoice
from tests.test_line_matching import env, expected_answer  # noqa: F401  (env is a fixture)
from tests.test_review import _item_id, _line, _override


def _finalize(env, invoice_id, no_match, price_flags, arithmetic_warnings=0):
    return env.client.post(f"/invoices/{invoice_id}/finalize", data={
        "no_match": no_match, "price_flags": price_flags, "arithmetic_warnings": arithmetic_warnings})


def test_summary_text(env):
    invoice_id = env.run()
    page = env.client.get(f"/invoices/{invoice_id}/finalize")
    assert page.status_code == 200
    assert "3 lines with no match, 1 price difference, 0 arithmetic warnings" in page.text


def test_finalize_stores_summary(env):
    invoice_id = env.run()
    assert _finalize(env, invoice_id, 3, 1).status_code == 303
    invoice = env.invoice(invoice_id)
    assert invoice.status == "finalized" and invoice.finalized_at
    summary = json.loads(invoice.finalize_summary)
    assert summary["text"] == "3 lines with no match, 1 price difference, 0 arithmetic warnings"
    assert (summary["no_match"], summary["price_flags"], summary["arithmetic_warnings"]) == (3, 1, 0)


def test_changed_counts_refused(env):
    invoice_id = env.run()
    response = _finalize(env, invoice_id, 2, 1)
    assert response.status_code == 409
    assert "3 lines with no match" in response.text
    assert env.invoice(invoice_id).status == "in_review"


def test_open_problems_allowed(env):
    invoice_id = env.run()
    _finalize(env, invoice_id, 3, 1)
    assert env.invoice(invoice_id).status == "finalized"


def test_finalize_wrong_status(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        s.get(Invoice, invoice_id).status = "matching_failed"
        s.commit()
    assert env.client.get(f"/invoices/{invoice_id}/finalize").status_code == 409
    assert _finalize(env, invoice_id, 3, 1).status_code == 409


def test_finalized_locked(env):
    invoice_id = env.run()
    _finalize(env, invoice_id, 3, 1)
    line, _ = _line(env, invoice_id, 1)
    for path, data in [
        (f"/invoices/{invoice_id}/confirm", {"sponsor_id": 1, "study_id": 1, "site_id": 3}),
        (f"/invoices/{invoice_id}/change-metadata", None),
        (f"/invoices/{invoice_id}/retry", None),
        (f"/invoices/{invoice_id}/lines/{line.id}/override", {"catalog_item_id": "none"}),
        (f"/invoices/{invoice_id}/lines/{line.id}/undo", None),
    ]:
        assert env.client.post(path, data=data).status_code == 409, path
    assert env.invoice(invoice_id).status == "finalized"


def test_export_before_finalize(env):
    invoice_id = env.run()
    assert env.client.get(f"/invoices/{invoice_id}/export.json").status_code == 409


def test_override_and_finalize_race(env):
    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 1)
    holding = threading.Event()
    results = {}

    def override_slowly():
        with env.client.app.state.sessions() as s:
            with locked_invoice(s, invoice_id, allowed={Status.IN_REVIEW}):
                holding.set()
                time.sleep(0.5)
                match = s.query(LineMatch).filter_by(line_item_id=line.id).one()
                match.override_kind = "no_match"

    def finalize_with_old_counts():
        holding.wait()
        results["status"] = _finalize(env, invoice_id, 3, 1).status_code

    threads = [threading.Thread(target=override_slowly), threading.Thread(target=finalize_with_old_counts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Finalize waited for the override, then saw 4 no-match lines, not the 3 it was shown: refused.
    assert results["status"] == 409
    assert env.invoice(invoice_id).status == "in_review"
    assert _finalize(env, invoice_id, 4, 1).status_code == 303


def test_export_contents(env):
    env.claude.match = expected_answer("medium_invoice")
    invoice_id = env.run("medium_invoice")
    _finalize(env, invoice_id, 0, 1)
    response = env.client.get(f"/invoices/{invoice_id}/export.json")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["invoice_number"] == "INV-2024-042" and data["invoice_date"] == "2024-06-20"
    assert data["original_filename"] == "medium-invoice.pdf"
    assert data["sponsor"] == {"id": 1, "name": "Northwind Pharma"}
    assert data["study"] == {"id": 1, "name": "LUMIN-2024"}
    assert data["site"] == {"id": 2, "name": "Harborview Medical Institute"}
    assert data["printed_total"] == "7145.00" and data["arithmetic_warnings"] == []
    assert len(data["lines"]) == 11
    for line in data["lines"]:
        assert set(line) >= {"position", "description", "quantity", "unit_price", "amount", "ai_suggestion",
                             "override", "final_item", "price_flag"}
        assert set(line["ai_suggestion"]) >= {"item_code", "confidence", "reason"}
    irb = data["lines"][10]
    assert irb["final_item"]["item_code"] == "ADMIN-IRB" and irb["price_flag"]["diff"] == "50.00"
    assert data["finalize_summary"]["text"] == "0 lines with no match, 1 price difference, 0 arithmetic warnings"
    assert data["finalize_summary"]["finalized_at"]


def test_export_with_override(env):
    invoice_id = env.run()
    ecg, _ = _line(env, invoice_id, 10)
    _override(env, invoice_id, ecg.id, _item_id(env, invoice_id, "PROC-ECG-Read"))
    admin, _ = _line(env, invoice_id, 1)
    _override(env, invoice_id, admin.id, "none")
    # ECG Interpretation is $55 against the invoice's $85, so the override adds a second price flag.
    assert _finalize(env, invoice_id, 4, 2).status_code == 303
    lines = env.client.get(f"/invoices/{invoice_id}/export.json").json()["lines"]
    assert lines[9]["ai_suggestion"]["item_code"] == "PROC-ECG"
    assert lines[9]["override"]["item_code"] == "PROC-ECG-Read"
    assert lines[9]["final_item"]["item_code"] == "PROC-ECG-Read"
    assert lines[0]["override"] == {"kind": "no_match", "item_code": None}
    assert lines[0]["final_item"] is None


def test_finalized_page_offers_download(env):
    invoice_id = env.run()
    review = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert f'href="/invoices/{invoice_id}/finalize"' in review
    _finalize(env, invoice_id, 3, 1)
    page = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert f'href="/invoices/{invoice_id}/export.json"' in page
    assert "3 lines with no match, 1 price difference, 0 arithmetic warnings" in page


def test_key_nowhere(env):
    from sqlalchemy import inspect, text

    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 10)
    _override(env, invoice_id, line.id, "none")
    pages = [env.client.get(p).text for p in ("/", f"/invoices/{invoice_id}", f"/invoices/{invoice_id}/finalize")]
    _finalize(env, invoice_id, 4, 1)
    pages += [env.client.get(f"/invoices/{invoice_id}").text, env.client.get(f"/invoices/{invoice_id}/export.json").text]
    assert all("SECRET123" not in page for page in pages)
    with env.client.app.state.sessions() as s:
        engine = s.get_bind()
        for table in inspect(engine).get_table_names():
            for row in s.execute(text(f"SELECT * FROM {table}")):
                assert "SECRET123" not in " ".join(str(v) for v in row), table


def test_download_name_is_cleaned(env):
    from tests.test_extraction_step import saved_extraction

    hostile = saved_extraction("large_invoice")
    hostile.header.invoice_number = 'INV"; evil=1\r\nX-Injected: yes/../../x'
    invoice_id = env.run(extraction=hostile)
    _finalize(env, invoice_id, 3, 1)
    response = env.client.get(f"/invoices/{invoice_id}/export.json")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="INV-evil-1-X-Injected-yes-..-..-x.json"'
    assert "x-injected" not in {k.lower() for k in response.headers}


def test_download_name_falls_back(env):
    from tests.test_extraction_step import saved_extraction

    blank = saved_extraction("large_invoice")
    blank.header.invoice_number = '"\r\n'
    invoice_id = env.run(extraction=blank)
    _finalize(env, invoice_id, 3, 1)
    assert env.client.get(f"/invoices/{invoice_id}/export.json").headers["content-disposition"] == (
        f'attachment; filename="invoice-{invoice_id}.json"')
