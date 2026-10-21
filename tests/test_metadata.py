import pytest

from app.schemas import ExtractedHeader
from app.steps.metadata import clean, lower_one_level, site_link_warning, suggest
from tests.fakes import reference_data
from tests.test_extraction_step import saved_extraction

DATA = reference_data()


def _suggest(**header):
    return {s.field: s for s in suggest(ExtractedHeader(**header), DATA)}


def test_clean():
    assert clean("  NORTHWIND  Pharma. ") == "northwind pharma"
    assert clean("Société Northwind") == "societe northwind"


def test_lower_one_level():
    assert [lower_one_level(c) for c in ("exact", "likely", "uncertain", "not_found")] == [
        "likely", "uncertain", "not_found", "not_found"
    ]


# Sponsors

def test_sponsor_exact():
    s = _suggest(sponsor_name="Contoso Therapeutics")["sponsor"]
    assert (s.confidence, s.entity_id) == ("exact", 2)


def test_sponsor_company_ending_is_likely_not_exact():
    s = _suggest(sponsor_name="Northwind Pharmaceuticals Inc.")["sponsor"]
    assert (s.confidence, s.entity_id) == ("likely", 1)
    assert "Sponsor name differs: invoice says 'Northwind Pharmaceuticals Inc.', closest is 'Northwind Pharma'." in s.reasons


@pytest.mark.parametrize("name", ["NORTHWIND  PHARMA", "Northwind Pharma."])
def test_sponsor_case_and_spacing_still_exact(name):
    s = _suggest(sponsor_name=name)["sponsor"]
    assert (s.confidence, s.entity_id) == ("exact", 1)


def test_sponsor_accents():
    s = _suggest(sponsor_name="Société Northwind Pharma")["sponsor"]
    assert (s.confidence, s.entity_id) == ("likely", 1)


def test_sponsor_not_found():
    s = _suggest(sponsor_name="Acme Widgets")["sponsor"]
    assert (s.confidence, s.entity_id) == ("not_found", None)


# Studies

def test_study_exact():
    s = _suggest(protocol_number="CON-CAT-2024-101", study_name="CATALYST Trial")["study"]
    assert (s.confidence, s.entity_id) == ("exact", 3)


def test_study_protocol_year_differs():
    s = _suggest(protocol_number="NWD-VER-2024-002", study_name="VERITAS Phase 2 Study")["study"]
    assert (s.confidence, s.entity_id) == ("likely", 2)
    assert (
        "Protocol NWD-VER-2024-002 is not in the reference data; closest is NWD-VER-2023-002 (VERITAS), "
        "which differs in the year."
    ) in s.reasons


def test_study_name_conflicts_with_exact_protocol():
    s = _suggest(protocol_number="NWD-LUM-2024-001", study_name="VERITAS")["study"]
    assert (s.confidence, s.entity_id) == ("likely", 1)
    assert any("study name points to VERITAS" in r for r in s.reasons)


# Sites

def test_site_exact():
    s = _suggest(site_name="Highland Ridge Hospital - Research Unit", site_city="Denver", site_state="CO",
                 pi_name="Dr. Taylor Reed")["site"]
    assert (s.confidence, s.entity_id) == ("exact", 3)


def test_site_near_miss_with_evidence():
    s = _suggest(site_name="Prairie Clinical Research", site_city="Kansas City", site_state="MO",
                 pi_name="Dr. Riley H. Foster")["site"]
    assert s.entity_id == 6 and s.confidence in ("likely", "uncertain")
    text = " ".join(s.reasons)
    assert "Prairie Clinical Research" in text and "Prairie Field Research Group" in text
    assert "Kansas City" in text and "Foster" in text


# Cross-checks

def test_sponsor_taken_from_study():
    s = _suggest(protocol_number="NWD-LUM-2024-001")["sponsor"]
    assert (s.confidence, s.entity_id) == ("likely", 1)
    assert "Sponsor taken from the matched study." in s.reasons


def test_study_belongs_to_other_sponsor():
    s = _suggest(sponsor_name="Contoso Therapeutics", protocol_number="NWD-LUM-2024-001", study_name="LUMIN-2024")["study"]
    assert any("LUMIN-2024 belongs to Northwind Pharma, not Contoso Therapeutics" in r for r in s.reasons)


def test_site_link_warning():
    warning = site_link_warning(1, 6, DATA)
    assert "Prairie Field Research Group" in warning and "LUMIN-2024" in warning
    assert site_link_warning(2, 6, DATA) is None


def test_unlinked_site_drops_one_level():
    s = _suggest(site_name="Prairie Field Research Group", protocol_number="NWD-LUM-2024-001")["site"]
    assert (s.confidence, s.entity_id) == ("likely", 6)
    assert site_link_warning(1, 6, DATA) in s.reasons


# The four sample invoices, against the spec's expected results

@pytest.mark.parametrize(
    "sample, expected",
    [
        ("simple_invoice", {"sponsor": (2, {"exact"}), "study": (3, {"exact"}), "site": (1, {"exact"})}),
        ("medium_invoice", {"sponsor": (1, {"exact"}), "study": (1, {"exact"}), "site": (2, {"exact"})}),
        ("large_invoice", {"sponsor": (1, {"exact"}), "study": (1, {"exact"}), "site": (3, {"exact"})}),
        (
            "mismatched_metadata_invoice",
            {"sponsor": (1, {"likely"}), "study": (2, {"likely"}), "site": (6, {"likely", "uncertain"})},
        ),
    ],
)
def test_samples(sample, expected):
    got = {s.field: s for s in suggest(saved_extraction(sample).header, DATA)}
    for field, (entity_id, levels) in expected.items():
        assert got[field].entity_id == entity_id, field
        assert got[field].confidence in levels, (field, got[field].confidence, got[field].reasons)


def test_near_protocol_with_conflicting_name():
    s = _suggest(protocol_number="NWD-LUM-2024-002", study_name="VERITAS Phase 2 Study")["study"]
    assert (s.confidence, s.entity_id) == ("uncertain", 1)
    assert any("study name points to VERITAS" in r for r in s.reasons)


def test_exact_site_name_with_conflicting_facts():
    s = _suggest(site_name="Highland Ridge Hospital - Research Unit", site_city="Kansas City", site_state="MO",
                 pi_name="Dr. Riley H. Foster")["site"]
    assert (s.confidence, s.entity_id) == ("likely", 3)
    assert any("Denver" in r and "Kansas City" in r for r in s.reasons)


def test_sponsor_from_study_never_above_study():
    found = _suggest(study_name="Veritaz Prog")
    assert found["study"].confidence == "uncertain"
    assert found["sponsor"].confidence == "uncertain"
    assert "Sponsor taken from the matched study." in found["sponsor"].reasons
