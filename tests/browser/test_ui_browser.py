"""Browser tests: a real Chromium, driven by Playwright, through the running app and the real Claude.

They cost money (about 20 cents) and need the whole stack running, so they run only when asked for:
    docker compose up -d --build
    .venv/bin/pytest -m browser -v
APP_URL picks another address than http://localhost:8080.
"""

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = json.loads((ROOT / "tests" / "fixtures" / "expected_results.json").read_text())
APP = os.environ.get("APP_URL", "http://localhost:8080")
READING = 180_000  # milliseconds to wait for Claude to read or match an invoice

# What the review summary should say for each sample: matched, no match, price flags.
SUMMARY = {
    "simple_invoice": "5 matched, 0 no match, 0 price flags, 0 overridden",
    "medium_invoice": "11 matched, 0 no match, 1 price flag, 0 overridden",
    "large_invoice": "24 matched, 3 no match, 1 price flag, 0 overridden",
    "mismatched_metadata_invoice": "7 matched, 0 no match, 0 price flags, 0 overridden",
}


@pytest.fixture
def errors(page: Page):
    """Every console error and uncaught exception the pages raise; each test checks it stays empty."""
    seen = []
    page.on("console", lambda m: seen.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: seen.append(str(e)))
    return seen


def upload_and_confirm(page: Page, sample: str) -> str:
    """Upload a sample, check the suggested sponsor, study and site, confirm, and wait for the review."""
    expected = EXPECTED[sample]
    page.goto(APP)
    page.set_input_files("#file", ROOT / "sample-invoices" / expected["file"])
    page.get_by_role("button", name="Upload and read").click()
    form = page.locator("#confirm-form")
    expect(form).to_be_visible(timeout=READING)
    url = page.url.split("?")[0]
    for field in ("sponsor", "study", "site"):
        expect(form.locator(f"select[name={field}_id]")).to_have_value(str(expected[field]["id"]))
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("p.summary")).to_be_visible(timeout=READING)
    expect(page.locator(".status").first).to_have_text("In review")
    return url


@pytest.mark.parametrize("sample", list(SUMMARY))
def test_sample_through_to_review(page: Page, errors, sample):
    upload_and_confirm(page, sample)
    expect(page.locator("p.summary")).to_have_text(SUMMARY[sample])
    for line in EXPECTED[sample]["lines"]:
        cell = page.locator(f"#line-{line['position']} td").nth(5)
        expect(cell).to_contain_text(line["item_code"] or "No match")
    assert errors == []


def test_changing_sponsor_keeps_the_study_picker(page: Page, errors):
    """Picking another sponsor refills the study list in place (it used to vanish)."""
    expected = EXPECTED["simple_invoice"]
    page.goto(APP)
    page.set_input_files("#file", ROOT / "sample-invoices" / expected["file"])
    page.get_by_role("button", name="Upload and read").click()
    form = page.locator("#confirm-form")
    expect(form).to_be_visible(timeout=READING)
    sponsor, study = form.locator("select[name=sponsor_id]"), form.locator("#study-select")
    other = next(v for v in sponsor.locator("option").evaluate_all("os => os.map(o => o.value)")
                 if v and v != str(expected["sponsor"]["id"]))
    sponsor.select_option(other)
    expect(study).to_be_visible()
    sponsor.select_option(str(expected["sponsor"]["id"]))
    expect(study.locator(f"option[value='{expected['study']['id']}']")).to_have_count(1)
    study.select_option(str(expected["study"]["id"]))
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("p.summary")).to_be_visible(timeout=READING)
    assert errors == []


def test_override_undo_finalize_and_download(page: Page, errors):
    expected = EXPECTED["medium_invoice"]
    url = upload_and_confirm(page, "medium_invoice")
    first, other = expected["lines"][0], expected["lines"][1]

    # Override line 1 by searching the catalog for another line's item, then undo it.
    row = page.locator(f"#line-{first['position']}")
    row.get_by_role("searchbox").fill(other["item_code"])
    picker = row.locator("select[name=catalog_item_id]")
    expect(picker.locator(f"option[value='{other['catalog_item_id']}']")).to_have_count(1)
    picker.select_option(str(other["catalog_item_id"]))
    row.get_by_role("button", name="Change").click()
    row = page.locator(f"#line-{first['position']}")
    expect(row).to_contain_text("Changed by a person")
    expect(row.locator("td").nth(5)).to_contain_text(other["item_code"])
    expect(page.locator("p.summary")).to_contain_text("1 overridden")
    row.get_by_role("button", name="Undo").click()
    expect(page.locator("p.summary")).to_have_text(SUMMARY["medium_invoice"])

    # Finalize with the open problems stated, then download the JSON.
    page.get_by_role("link", name="Finalize").click()
    expect(page.locator("h1")).to_have_text("Finalize this invoice?")
    expect(page.get_by_text("0 lines with no match, 1 price difference, 0 arithmetic warnings")).to_be_visible()
    page.get_by_role("button", name="Confirm and finalize").click()
    expect(page.locator(".status").first).to_have_text("Finalized")
    with page.expect_download() as download:
        page.get_by_role("link", name="Download JSON").click()
    data = json.loads(Path(download.value.path()).read_text())
    assert [line["final_item"]["item_code"] for line in data["lines"]] == [l["item_code"] for l in expected["lines"]]
    assert data["lines"][0]["override"] is None
    assert data["finalize_summary"]["price_flags"] == 1

    # A finalized invoice can't be changed. (Its finalize page answers 409, which the browser logs.)
    assert errors == []
    expect(page.get_by_role("button", name="Change")).to_have_count(0)
    response = page.goto(url + "/finalize")
    assert response.status == 409
    expect(page.get_by_text("finalized and can't be changed")).to_be_visible()


def test_unknown_invoice_page(page: Page):
    response = page.goto(f"{APP}/invoices/999999")
    assert response.status == 404
    expect(page.get_by_text("There's no invoice with that number.")).to_be_visible()
    page.get_by_role("link", name="Back to all invoices").click()
    expect(page.get_by_role("button", name="Upload and read")).to_be_visible()


def test_phone_width_has_no_sideways_scroll(page: Page):
    page.set_viewport_size({"width": 375, "height": 800})
    url = upload_and_confirm(page, "large_invoice")
    for address in (APP, url, url + "/finalize"):
        page.goto(address)
        assert page.evaluate("document.documentElement.scrollWidth") <= 375, address
