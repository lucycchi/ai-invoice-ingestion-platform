import json
from html import unescape

from app.models import Invoice, LineItem, LineMatch, Run
from app.web.review import review_summary
from tests.test_line_matching import env, expected_answer  # noqa: F401  (env is a fixture)


def _line(env, invoice_id, position):
    with env.client.app.state.sessions() as s:
        line = s.query(LineItem).filter_by(invoice_id=invoice_id, position=position).one()
        return line, s.query(LineMatch).filter_by(line_item_id=line.id).one_or_none()


def _item_id(env, invoice_id, code):
    from app.models import CatalogSnapshotItem

    with env.client.app.state.sessions() as s:
        return s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id, item_code=code).one().catalog_item_id


def _summary(env, invoice_id):
    with env.client.app.state.sessions() as s:
        return review_summary(s, invoice_id)


def _override(env, invoice_id, line_id, value):
    return env.client.post(f"/invoices/{invoice_id}/lines/{line_id}/override", data={"catalog_item_id": value})


def test_progress_counts(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        s.get(Invoice, invoice_id).status = "matching"
        lines = s.query(LineItem).filter_by(invoice_id=invoice_id).order_by(LineItem.position).all()
        for line in lines[12:]:
            s.query(LineMatch).filter_by(line_item_id=line.id).delete()
        s.commit()
    part = env.client.get(f"/invoices/{invoice_id}/progress")
    assert "Matching line items: 12 of 27 done" in part.text
    assert part.text.count('class="line-row') == 12
    assert "HX-Refresh" not in part.headers


def test_progress_redirects_when_done(env):
    invoice_id = env.run()
    response = env.client.get(f"/invoices/{invoice_id}/progress")
    assert response.headers.get("HX-Redirect") == f"/invoices/{invoice_id}?from=matching"


def test_review_rows(env):
    invoice_id = env.run()
    page = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert page.count('class="line-row') == 27
    assert page.index("Site Admin") < page.index("Translator Services")
    assert "Invoice $475.00, catalog $450.00, +$25.00 (+5.6%)" in page
    assert page.count("line-row no-match") == 3
    assert "24 matched, 3 no match, 1 price flag, 0 overridden" in page


def test_catalog_search(env):
    invoice_id = env.run()
    part = env.client.get(f"/invoices/{invoice_id}/catalog?q=ecg").text
    for code in ("PROC-ECG", "PROC-ECG-Read", "PROC-ECG-HOLTER"):
        assert f">{code} " in part
    assert "VISIT-SCR" not in part


def test_override_and_undo(env):
    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 10)
    ecg_read = _item_id(env, invoice_id, "PROC-ECG-Read")
    assert _override(env, invoice_id, line.id, ecg_read).status_code == 303
    _, match = _line(env, invoice_id, 10)
    assert (match.override_kind, match.override_catalog_item_id) == ("item", ecg_read)
    assert match.ai_catalog_item_id == _item_id(env, invoice_id, "PROC-ECG")
    page = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert "Changed by a person" in page and "1 overridden" in page
    assert env.client.post(f"/invoices/{invoice_id}/lines/{line.id}/undo").status_code == 303
    _, match = _line(env, invoice_id, 10)
    assert match.override_kind == "none"
    assert "0 overridden" in unescape(env.client.get(f"/invoices/{invoice_id}").text)


def test_override_no_match_clears_flag(env):
    invoice_id = env.run()
    line, match = _line(env, invoice_id, 20)
    assert match.price_flag
    _override(env, invoice_id, line.id, "none")
    _, match = _line(env, invoice_id, 20)
    assert (match.override_kind, match.price_flag) == ("no_match", None)


def test_override_refused_when_finalized(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        s.get(Invoice, invoice_id).status = "finalized"
        s.commit()
    line, _ = _line(env, invoice_id, 1)
    assert _override(env, invoice_id, line.id, "none").status_code == 409
    _, match = _line(env, invoice_id, 1)
    assert match.override_kind == "none"


def test_override_foreign_line(env):
    first = env.run()
    second = env.run()
    line, _ = _line(env, second, 1)
    assert _override(env, first, line.id, "none").status_code == 404
    _, match = _line(env, second, 1)
    assert match.override_kind == "none"


def test_override_item_not_in_catalog(env):
    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 1)
    catalyst_item = 112  # an item from the CATALYST Trial catalog, not this invoice's snapshot
    assert _override(env, invoice_id, line.id, catalyst_item).status_code == 422
    _, match = _line(env, invoice_id, 1)
    assert match.override_kind == "none"


def test_shown_only_after_stored(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        run = s.query(Run).filter_by(invoice_id=invoice_id, step="matching").one()
        stored_at, run.stored_at = run.stored_at, None
        s.get(Invoice, invoice_id).status = "matching"
        s.commit()
    assert env.client.post(f"/invoices/{invoice_id}/shown").status_code == 409
    with env.client.app.state.sessions() as s:
        s.query(Run).filter_by(invoice_id=invoice_id, step="matching").one().stored_at = stored_at
        s.get(Invoice, invoice_id).status = "in_review"
        s.commit()
    assert env.client.post(f"/invoices/{invoice_id}/shown").status_code == 200
    first = env.matching_run(invoice_id).shown_at
    assert first
    env.client.post(f"/invoices/{invoice_id}/shown")
    assert env.matching_run(invoice_id).shown_at == first


def test_escapes_invoice_text(env):
    from tests.test_extraction_step import saved_extraction

    hostile = saved_extraction("large_invoice")
    hostile.lines[0].description = "<script>alert(1)</script>"
    invoice_id = env.run(extraction=hostile)
    page = env.client.get(f"/invoices/{invoice_id}").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)" not in page


def test_shows_times(env):
    invoice_id = env.run()
    env.client.post(f"/invoices/{invoice_id}/shown")
    page = env.client.get(f"/invoices/{invoice_id}").text
    assert "Reading took" in page and "Matching took" in page and "on screen" in page


def test_summary_counts(env):
    invoice_id = env.run()
    summary = _summary(env, invoice_id)
    assert (summary.matched, summary.no_match, summary.price_flags, summary.overridden, summary.arithmetic_warnings) == (
        24, 3, 1, 0, 0)


def test_picker_starts_on_current_item(env):
    import re

    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 1)
    page = env.client.get(f"/invoices/{invoice_id}").text
    picker = re.search(rf'<select id="picker-{line.id}".*?</select>', page, re.S).group(0)
    selected = re.findall(r'<option value="([^"]+)" selected>', picker)
    assert selected == [str(_item_id(env, invoice_id, "ADMIN-SITE"))]
    no_match_line, _ = _line(env, invoice_id, 25)
    picker = re.search(rf'<select id="picker-{no_match_line.id}".*?</select>', page, re.S).group(0)
    assert re.findall(r'<option value="([^"]+)" selected>', picker) == ["none"]


def test_choosing_the_ai_item_is_no_override(env):
    invoice_id = env.run()
    line, match = _line(env, invoice_id, 10)
    _override(env, invoice_id, line.id, match.ai_catalog_item_id)
    assert _line(env, invoice_id, 10)[1].override_kind == "none"
    _override(env, invoice_id, line.id, _item_id(env, invoice_id, "PROC-ECG-Read"))
    _override(env, invoice_id, line.id, match.ai_catalog_item_id)
    assert _line(env, invoice_id, 10)[1].override_kind == "none"
    assert _summary(env, invoice_id).overridden == 0


def test_search_results_need_a_choice(env):
    invoice_id = env.run()
    part = env.client.get(f"/invoices/{invoice_id}/catalog?q=ecg").text
    assert part.lstrip().startswith('<option value="" selected>Choose an item')
    line, _ = _line(env, invoice_id, 10)
    assert _override(env, invoice_id, line.id, "").status_code == 422
    assert _line(env, invoice_id, 10)[1].override_kind == "none"


def test_failed_screen_lists_every_line(env):
    from tests.test_line_matching import _bad_for

    env.claude.match = _bad_for(set(range(7, 13)), expected_answer("large_invoice"))
    invoice_id = env.run()
    page = unescape(env.client.get(f"/invoices/{invoice_id}").text)
    assert page.count('class="line-row') == 27
    assert page.count("No result yet") == 6
    assert "Matching took" not in page


def test_shown_recorded_only_from_live_matching(env):
    invoice_id = env.run()
    assert 'hx-post="/invoices/' not in env.client.get(f"/invoices/{invoice_id}").text
    assert f'hx-post="/invoices/{invoice_id}/shown"' in env.client.get(f"/invoices/{invoice_id}?from=matching").text


def test_shown_returns_the_updated_time(env):
    invoice_id = env.run()
    response = env.client.post(f"/invoices/{invoice_id}/shown")
    assert "on screen" in response.text


def test_concurrent_shown_reports_keep_the_first(env):
    import threading

    invoice_id = env.run()
    barrier = threading.Barrier(4)

    def report():
        barrier.wait()
        env.client.post(f"/invoices/{invoice_id}/shown")

    threads = [threading.Thread(target=report) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    first = env.matching_run(invoice_id).shown_at
    env.client.post(f"/invoices/{invoice_id}/shown")
    assert env.matching_run(invoice_id).shown_at == first
