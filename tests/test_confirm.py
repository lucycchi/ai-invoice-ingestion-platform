import json
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import CatalogSnapshotItem, Invoice, LineItem, LineMatch, Run
from tests.conftest import REPO_ROOT
from tests.fakes import FakeClaude, FakeReference
from tests.test_extraction_step import saved_extraction

SAMPLES = {
    "simple_invoice": "simple-invoice.pdf",
    "medium_invoice": "medium-invoice.pdf",
    "large_invoice": "large-invoice.pdf",
    "mismatched_metadata_invoice": "mismatched-metadata-invoice.pdf",
}


@pytest.fixture
def env(settings):
    from app.schemas import GroupAnswer, LineResult

    # Matching answers "no match" for every line; these tests are about confirmation, not matching.
    no_match = lambda number, lines: GroupAnswer(results=[
        LineResult(position=line["position"], catalog_item_id=None, confidence="low", reason="r", alternatives=[])
        for line in lines])
    claude = FakeClaude(extraction=saved_extraction("simple_invoice"), match=no_match)
    reference = FakeReference()
    with TestClient(create_app(settings, claude=claude, reference=reference), follow_redirects=False) as client:
        yield client, claude, reference


def _upload(env, sample="simple_invoice") -> int:
    client, claude, _ = env
    claude.extraction = saved_extraction(sample)
    data = (REPO_ROOT / "sample-invoices" / SAMPLES[sample]).read_bytes()
    response = client.post("/invoices", files={"file": (SAMPLES[sample], data)})
    return int(response.headers["location"].rsplit("/", 1)[1])


def _invoice(env, invoice_id) -> Invoice:
    with env[0].app.state.sessions() as s:
        return s.get(Invoice, invoice_id)


def _set_status(env, invoice_id, status):
    with env[0].app.state.sessions() as s:
        s.get(Invoice, invoice_id).status = status
        s.commit()


def _confirm(env, invoice_id, sponsor, study, site):
    return env[0].post(f"/invoices/{invoice_id}/confirm", data={"sponsor_id": sponsor, "study_id": study, "site_id": site})


def test_screen_shows_suggestions(env):
    page = env[0].get(f"/invoices/{_upload(env, 'mismatched_metadata_invoice')}").text
    assert page.count(">likely<") == 3
    assert "Northwind Pharma" in page and "VERITAS" in page
    assert "differs in the year" in page


def test_screen_shows_reading(env):
    page = env[0].get(f"/invoices/{_upload(env)}").text
    assert "INV-2024-001" in page and "2024-03-15" in page
    for description in ("Site Management Fee", "Screening Visit", "Baseline Visit", "Complete Blood Count",
                        "IV Infusion Administration"):
        assert description in page
    assert "The arithmetic checks passed." in page


def test_studies_filtered(env):
    part = env[0].get(f"/invoices/{_upload(env)}/studies?sponsor_id=2").text
    assert "CATALYST Trial" in part and "AURORA Extension" in part
    assert "LUMIN-2024" not in part and "VERITAS" not in part


def test_confirm_starts_matching(env):
    invoice_id = _upload(env)
    response = _confirm(env, invoice_id, 2, 3, 1)
    # The page after Confirm follows matching live, so it may report when the results are on screen.
    assert response.status_code == 303 and response.headers["location"] == f"/invoices/{invoice_id}?from=matching"
    invoice = _invoice(env, invoice_id)
    assert invoice.status == "in_review"  # matching ran in the background after Confirm
    assert (invoice.confirmed_sponsor_id, invoice.confirmed_study_id, invoice.confirmed_site_id) == (2, 3, 1)
    assert json.loads(invoice.confirmed_names) == {
        "sponsor": "Contoso Therapeutics", "study": "CATALYST Trial", "site": "Willow Creek Clinical Research Center"
    }
    with env[0].app.state.sessions() as s:
        [run] = s.query(Run).filter_by(invoice_id=invoice_id, step="matching").all()
    assert run.started_at


def test_double_confirm_refused(env):
    invoice_id = _upload(env)
    _confirm(env, invoice_id, 2, 3, 1)
    _set_status(env, invoice_id, "matching")  # as if the second click arrived while matching ran
    response = _confirm(env, invoice_id, 2, 3, 1)
    assert response.status_code == 409
    assert "Matching line items is already running" in response.text


def test_back_button_resubmit_friendly(env):
    invoice_id = _upload(env)
    _confirm(env, invoice_id, 2, 3, 1)
    _set_status(env, invoice_id, "matching")
    response = _confirm(env, invoice_id, 2, 3, 1)
    assert response.headers["content-type"].startswith("text/html")
    assert f'href="/invoices/{invoice_id}"' in response.text


def test_confirm_wrong_status(env):
    invoice_id = _upload(env)
    _set_status(env, invoice_id, "extracting")
    assert _confirm(env, invoice_id, 2, 3, 1).status_code == 409
    assert _invoice(env, invoice_id).status == "extracting"


def test_confirm_study_wrong_sponsor(env):
    invoice_id = _upload(env)
    response = _confirm(env, invoice_id, 2, 2, 1)
    assert response.status_code == 422
    assert "VERITAS belongs to Northwind Pharma, not Contoso Therapeutics." in unescape(response.text)
    assert _invoice(env, invoice_id).status == "awaiting_confirmation"


@pytest.mark.parametrize("ids, message", [
    ((2, 3, 99), "Site 99 isn't in the reference data."),
    ((99, 3, 1), "Sponsor 99 isn't in the reference data."),
    ((2, 99, 1), "Study 99 isn't in the reference data."),
])
def test_confirm_unknown_choice(env, ids, message):
    invoice_id = _upload(env)
    response = _confirm(env, invoice_id, *ids)
    assert response.status_code == 422 and message in unescape(response.text)
    assert _invoice(env, invoice_id).status == "awaiting_confirmation"


def test_confirm_reference_down(env):
    invoice_id = _upload(env)
    env[2].down = True
    response = _confirm(env, invoice_id, 2, 3, 1)
    assert response.status_code == 503
    assert "Couldn't reach the reference API at http://api:8000" in unescape(response.text)
    assert _invoice(env, invoice_id).status == "awaiting_confirmation"


def test_site_link_warning_redrawn(env):
    invoice_id = _upload(env)
    unlinked = unescape(env[0].get(f"/invoices/{invoice_id}/warnings?sponsor_id=1&study_id=1&site_id=6").text)
    linked = unescape(env[0].get(f"/invoices/{invoice_id}/warnings?sponsor_id=1&study_id=1&site_id=3").text)
    assert "isn't listed as taking part in LUMIN-2024" in unlinked
    assert "isn't listed" not in linked


def test_duplicate_warning(env):
    earlier = _upload(env, "medium_invoice")
    _confirm(env, earlier, 1, 1, 2)
    _set_status(env, earlier, "finalized")
    later = _upload(env, "medium_invoice")
    same_site = env[0].get(f"/invoices/{later}/warnings?sponsor_id=1&study_id=1&site_id=2").text
    other_site = env[0].get(f"/invoices/{later}/warnings?sponsor_id=1&study_id=1&site_id=3").text
    assert "INV-2024-042" in same_site and "medium-invoice.pdf" in same_site
    assert "INV-2024-042" not in other_site


def _override_some(env, invoice_id, overridden=2):
    """Mark the first matches as overridden by a person (matching itself ran after Confirm)."""
    with env[0].app.state.sessions() as s:
        matches = (s.query(LineMatch).join(LineItem, LineMatch.line_item_id == LineItem.id)
                   .filter(LineItem.invoice_id == invoice_id).order_by(LineItem.position).limit(overridden).all())
        for match in matches:
            match.override_kind = "no_match"
        s.commit()


def _count(env, model, **where):
    with env[0].app.state.sessions() as s:
        return s.query(model).filter_by(**where).count()


def test_change_metadata_warns_and_clears(env):
    invoice_id = _upload(env, "large_invoice")
    _confirm(env, invoice_id, 1, 1, 3)
    assert _invoice(env, invoice_id).status == "in_review"
    assert _count(env, CatalogSnapshotItem, invoice_id=invoice_id) == 100
    _override_some(env, invoice_id)
    assert "This will clear 27 matches and 2 overrides" in env[0].get(f"/invoices/{invoice_id}/change-metadata").text
    response = env[0].post(f"/invoices/{invoice_id}/change-metadata")
    assert response.status_code == 303
    assert _invoice(env, invoice_id).status == "awaiting_confirmation"
    assert _count(env, LineMatch) == 0
    assert _count(env, CatalogSnapshotItem, invoice_id=invoice_id) == 0
    assert _count(env, LineItem, invoice_id=invoice_id) == 27


def test_change_metadata_refused_while_matching(env):
    invoice_id = _upload(env)
    _confirm(env, invoice_id, 2, 3, 1)
    _set_status(env, invoice_id, "matching")
    assert env[0].post(f"/invoices/{invoice_id}/change-metadata").status_code == 409


def test_nothing_auto_confirmed(env):
    assert _invoice(env, _upload(env)).status == "awaiting_confirmation"


def test_offer_study_sponsor(env):
    from app.models import MetadataSuggestion

    invoice_id = _upload(env)
    with env[0].app.state.sessions() as s:
        study = s.query(MetadataSuggestion).filter_by(invoice_id=invoice_id, field="study").one()
        study.entity_id, study.entity_name = 1, "LUMIN-2024"
        s.commit()
    page = env[0].get(f"/invoices/{invoice_id}").text
    assert "Use Northwind Pharma" in page
    prefilled = env[0].get(f"/invoices/{invoice_id}?sponsor_id=1&study_id=1").text
    assert 'value="1" selected' in prefilled


def test_warnings_shown_on_first_load(env):
    from app.models import MetadataSuggestion

    invoice_id = _upload(env, "large_invoice")
    with env[0].app.state.sessions() as s:
        site = s.query(MetadataSuggestion).filter_by(invoice_id=invoice_id, field="site").one()
        site.entity_id, site.entity_name = 6, "Prairie Field Research Group"
        s.commit()
    assert "isn't listed as taking part in LUMIN-2024" in unescape(env[0].get(f"/invoices/{invoice_id}").text)


def test_duplicate_shown_on_first_load(env):
    earlier = _upload(env, "medium_invoice")
    _confirm(env, earlier, 1, 1, 2)
    later = _upload(env, "medium_invoice")
    page = unescape(env[0].get(f"/invoices/{later}").text)
    assert "An earlier upload, medium-invoice.pdf" in page


def test_duplicate_ignores_later_uploads(env):
    first = _upload(env, "medium_invoice")
    second = _upload(env, "medium_invoice")
    _confirm(env, second, 1, 1, 2)
    part = env[0].get(f"/invoices/{first}/warnings?sponsor_id=1&study_id=1&site_id=2").text
    assert "INV-2024-042" not in part


def test_change_metadata_clears_confirmed_choice(env):
    invoice_id = _upload(env)
    _confirm(env, invoice_id, 2, 3, 1)
    _set_status(env, invoice_id, "in_review")
    env[0].post(f"/invoices/{invoice_id}/change-metadata")
    invoice = _invoice(env, invoice_id)
    assert (invoice.confirmed_sponsor_id, invoice.confirmed_study_id, invoice.confirmed_site_id) == (None, None, None)


def test_status_checked_before_choices(env):
    invoice_id = _upload(env)
    _set_status(env, invoice_id, "finalized")
    assert _confirm(env, invoice_id, 99, 99, 99).status_code == 409
    env[2].down = True
    assert _confirm(env, invoice_id, 2, 3, 1).status_code == 409


def test_owner_lookup_outage_is_503(env):
    invoice_id = _upload(env)
    reference = env[2]
    original = reference.get_sponsor
    calls = {"n": 0}

    def flaky(sponsor_id):
        calls["n"] += 1
        if calls["n"] > 1:
            reference.down = True
        return original(sponsor_id)

    reference.get_sponsor = flaky
    response = _confirm(env, invoice_id, 2, 2, 1)
    assert response.status_code == 503
    assert "Couldn't reach the reference API" in unescape(response.text)


def test_study_picker_outage(env):
    invoice_id = _upload(env)
    env[2].down = True
    response = env[0].get(f"/invoices/{invoice_id}/studies?sponsor_id=2")
    assert response.status_code == 503
    assert "Couldn't reach the reference API" in unescape(response.text)


# Regression: ISSUE-001 — changing the sponsor picker made the study picker disappear
# Found by /qa on 2026-10-20
# Report: .gstack/qa-reports/run-20261021T023335Z/qa-report-localhost-2026-10-20.md
def test_sponsor_picker_fills_the_study_picker_in_place(env):
    import re

    page = env[0].get(f"/invoices/{_upload(env)}").text
    sponsor = re.search(r'<select name="sponsor_id"[^>]*>', page).group(0)
    # The form swaps its warnings with outerHTML, and htmx attributes are inherited: without its own
    # swap, the sponsor picker would replace the whole study <select> with bare <option>s.
    assert 'hx-target="#study-select"' in sponsor and 'hx-swap="innerHTML"' in sponsor
