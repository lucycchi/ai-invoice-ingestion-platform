"""What the screens say and where things are, after the UI review of the finished app."""

import json
import re
from html import unescape

from tests.test_confirm import _confirm, _upload, env as confirm_env  # noqa: F401  (a fixture)
from tests.test_finalize import _finalize
from tests.test_line_matching import env  # noqa: F401  (a fixture)
from tests.test_review import _item_id, _line, _override


def test_review_page_shows_the_confirmed_metadata(env):
    invoice_id = env.run()
    names = json.loads(env.invoice(invoice_id).confirmed_names)
    page = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert "Confirmed" in page
    for name in names.values():
        assert name in page
    assert page.index(names["site"]) < page.index("Line items")


def test_overridden_line_marks_the_ai_columns(env):
    invoice_id = env.run()
    page = env.client.get(f"/invoices/{invoice_id}").text
    assert "AI confidence" in page and "AI reason" in page
    line, _ = _line(env, invoice_id, 10)
    _override(env, invoice_id, line.id, _item_id(env, invoice_id, "PROC-ECG-Read"))
    row = re.search(r'<tr id="line-10".*?</tr>', env.client.get(f"/invoices/{invoice_id}").text, re.S).group(0)
    assert row.count("superseded") == 2


def test_refused_line_change_has_its_own_title(env):
    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 10)
    page = unescape(_override(env, invoice_id, line.id, "").text)
    assert "That change wasn't made" in page and "Confirm wasn't accepted" not in page


def test_finalized_page_puts_status_and_download_first(env):
    invoice_id = env.run()
    _finalize(env, invoice_id, 3, 1)
    page = env.client.get(f"/invoices/{invoice_id}").text
    assert page.index("Download JSON") < page.index("Line items")


def test_times_are_readable(env):
    invoice_id = env.run()
    _finalize(env, invoice_id, 3, 1)
    for page in (env.client.get("/").text, env.client.get(f"/invoices/{invoice_id}").text):
        assert not re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d", page)
        assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", page)


def test_several_earlier_copies_give_one_duplicate_warning(confirm_env):
    for _ in range(2):
        earlier = _upload(confirm_env, "medium_invoice")
        _confirm(confirm_env, earlier, 1, 1, 2)
    later = _upload(confirm_env, "medium_invoice")
    part = unescape(confirm_env[0].get(f"/invoices/{later}/warnings?sponsor_id=1&study_id=1&site_id=2").text)
    assert part.count("may be a duplicate") == 1
    assert "2 earlier uploads" in part
