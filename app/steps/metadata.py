"""Step 2: suggest the sponsor, study and site in plain code, with confidence levels and reasons.

Rules (from the architecture's metadata section):
- Text is cleaned first: lower case, accents and punctuation removed, spaces collapsed.
- Exact means equal after cleaning (or the same protocol number). Company endings never count for exact.
- Otherwise a similarity score (rapidfuzz token set ratio, company endings removed) gives likely at
  85 or more with a 10-point lead over the runner-up, uncertain from 60, and not found below 60.
- A protocol that differs from a real one in exactly one segment is likely, with that segment named.
- For sites, the same city and state and the same investigator surname can lift the level by one.
- The three suggestions are then checked against each other.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.clients.reference_api import ReferenceData
from app.schemas import ExtractedHeader

LEVELS = ["not_found", "uncertain", "likely", "exact"]
LIKELY_SCORE = 85
UNCERTAIN_SCORE = 60
LEAD = 10
COMPANY_ENDINGS = {"inc", "ltd", "llc", "co", "corp", "company", "pharmaceuticals", "pharma", "therapeutics",
                   "biopharma", "life", "sciences"}


@dataclass
class Suggestion:
    field: str
    entity_id: int | None
    entity_name: str | None
    confidence: str
    reasons: list[str] = field(default_factory=list)


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _without_endings(cleaned: str) -> str:
    words = [w for w in cleaned.split() if w not in COMPANY_ENDINGS]
    return " ".join(words) or cleaned


def _score(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b)


def lower_one_level(confidence: str) -> str:
    return LEVELS[max(0, LEVELS.index(confidence) - 1)]


def _raise_one_level(confidence: str) -> str:
    return LEVELS[min(LEVELS.index("likely"), LEVELS.index(confidence) + 1)]


def _level(best: float, runner_up: float) -> str:
    if best >= LIKELY_SCORE and best - runner_up >= LEAD:
        return "likely"
    if best >= UNCERTAIN_SCORE:
        return "uncertain"
    return "not_found"


def _ranked(records: list[dict], key) -> list[tuple[float, dict]]:
    return sorted(((key(r), r) for r in records), key=lambda pair: -pair[0])


def _by_id(records: list[dict], record_id: int | None) -> dict | None:
    return next((r for r in records if r["id"] == record_id), None)


# Sponsor

def _suggest_sponsor(header: ExtractedHeader, data: ReferenceData) -> Suggestion:
    printed = header.sponsor_name
    if not printed:
        return Suggestion("sponsor", None, None, "not_found", ["No sponsor name is printed on the invoice."])
    wanted = clean(printed)
    for sponsor in data.sponsors:
        if wanted in (clean(sponsor["name"]), clean(sponsor["code"])):
            return Suggestion("sponsor", sponsor["id"], sponsor["name"], "exact", ["Sponsor name matches exactly."])
    ranked = _ranked(data.sponsors, lambda s: _score(_without_endings(wanted), _without_endings(clean(s["name"]))))
    (best, sponsor), runner_up = ranked[0], ranked[1][0] if len(ranked) > 1 else 0
    level = _level(best, runner_up)
    if level == "not_found":
        return Suggestion("sponsor", None, None, "not_found", [f"No sponsor in the reference data is close to '{printed}'."])
    reason = f"Sponsor name differs: invoice says '{printed}', closest is '{sponsor['name']}'."
    return Suggestion("sponsor", sponsor["id"], sponsor["name"], level, [reason])


# Study

def _segments_differing(a: str, b: str) -> list[int] | None:
    sa, sb = a.upper().split("-"), b.upper().split("-")
    if len(sa) != len(sb):
        return None
    return [i for i, (x, y) in enumerate(zip(sa, sb)) if x != y]


def _segment_name(printed: str, real: str, index: int) -> str:
    x, y = printed.split("-")[index], real.split("-")[index]
    if x.isdigit() and y.isdigit() and len(x) == len(y) == 4:
        return "the year"
    return f"part {index + 1} ('{x}' instead of '{y}')"


def _name_points_elsewhere(name, name_scores: dict, study_id: int, data: ReferenceData) -> dict | None:
    """Another study whose name fits the printed study name clearly better than `study_id` does."""
    if not name:
        return None
    others = [(score, sid) for sid, score in name_scores.items() if sid != study_id]
    best, best_id = max(others, default=(0, None))
    if best >= LIKELY_SCORE and best > name_scores[study_id] + LEAD:
        return _by_id(data.studies, best_id)
    return None


def _suggest_study(header: ExtractedHeader, data: ReferenceData) -> Suggestion:
    protocol, name = header.protocol_number, header.study_name
    name_scores = {s["id"]: _score(clean(name), clean(s["name"])) for s in data.studies} if name else {}

    exact = next((s for s in data.studies if protocol and s["protocol_number"].upper() == protocol.strip().upper()), None)
    if exact:
        other = _name_points_elsewhere(name, name_scores, exact["id"], data)
        if other:
            reason = (f"Protocol {exact['protocol_number']} matches {exact['name']} exactly, but the study name "
                      f"points to {other['name']}.")
            return Suggestion("study", exact["id"], exact["name"], "likely", [reason])
        return Suggestion("study", exact["id"], exact["name"], "exact", [f"Protocol {exact['protocol_number']} matches exactly."])

    if protocol:
        near = [(s, d) for s in data.studies if (d := _segments_differing(protocol.strip(), s["protocol_number"])) and len(d) == 1]
        if len(near) == 1:
            study, (index,) = near[0]
            reason = (f"Protocol {protocol} is not in the reference data; closest is {study['protocol_number']} "
                      f"({study['name']}), which differs in {_segment_name(protocol.strip(), study['protocol_number'], index)}.")
            other = _name_points_elsewhere(name, name_scores, study["id"], data)
            if other:
                return Suggestion("study", study["id"], study["name"], "uncertain",
                                  [reason, f"But the study name points to {other['name']}."])
            return Suggestion("study", study["id"], study["name"], "likely", [reason])

    if name:
        ranked = sorted(name_scores.items(), key=lambda pair: -pair[1])
        (best_id, best), runner_up = ranked[0], ranked[1][1] if len(ranked) > 1 else 0
        level = _level(best, runner_up)
        if level != "not_found":
            study = _by_id(data.studies, best_id)
            what = f"Protocol {protocol} is not in the reference data; " if protocol else "No protocol number is printed; "
            return Suggestion("study", study["id"], study["name"], level,
                              [f"{what}the study name '{name}' is closest to {study['name']}."])
    printed = protocol or name
    reason = (f"No study in the reference data is close to '{printed}'." if printed
              else "No protocol number or study name is printed on the invoice.")
    return Suggestion("study", None, None, "not_found", [reason])


# Site

def _surname(person: str | None) -> str:
    words = [w for w in clean(person).split() if w not in {"dr", "md", "phd", "prof"}]
    return words[-1] if words else ""


def _evidence(header: ExtractedHeader, site: dict) -> list[str]:
    found = []
    if header.site_city and clean(header.site_city) == clean(site.get("city")) and \
            header.site_state and clean(header.site_state) == clean(site.get("state")):
        found.append(f"the same city and state ({site['city']}, {site['state']})")
    surname = _surname(header.pi_name)
    if surname and surname == _surname(site.get("pi_name")):
        found.append(f"the same principal investigator surname ({site['pi_name'].split()[-1]})")
    return found


def _conflicts(header: ExtractedHeader, site: dict) -> list[str]:
    """Printed facts that disagree with the site record, as one plain phrase (empty if none)."""
    parts = []
    if header.site_city and header.site_state and (
        clean(header.site_city) != clean(site.get("city")) or clean(header.site_state) != clean(site.get("state"))
    ):
        parts.append(f"{header.site_city}, {header.site_state}")
    if header.pi_name and _surname(header.pi_name) != _surname(site.get("pi_name")):
        parts.append(header.pi_name)
    return [" and ".join(parts)] if parts else []


def _suggest_site(header: ExtractedHeader, data: ReferenceData) -> Suggestion:
    printed = header.site_name
    if not printed:
        return Suggestion("site", None, None, "not_found", ["No site name is printed on the invoice."])
    wanted = clean(printed)
    for site in data.sites:
        if wanted == clean(site["name"]):
            conflicts = _conflicts(header, site)
            if conflicts:
                return Suggestion("site", site["id"], site["name"], "likely", [
                    f"Site name matches exactly, but the invoice gives {conflicts[0]}; {site['name']} is in "
                    f"{site['city']}, {site['state']} with {site['pi_name']}."
                ])
            return Suggestion("site", site["id"], site["name"], "exact", ["Site name matches exactly."])
    ranked = _ranked(data.sites, lambda s: _score(wanted, clean(s["name"])) + 10 * len(_evidence(header, s)))
    (_, site) = ranked[0]
    name_score = _score(wanted, clean(site["name"]))
    runner_up_score = max((_score(wanted, clean(s["name"])) for _, s in ranked[1:]), default=0)
    level = _level(name_score, runner_up_score)
    evidence = _evidence(header, site)
    if len(evidence) >= 2 or (len(evidence) == 1 and level != "not_found"):
        level = _raise_one_level(level)
    if level == "not_found":
        return Suggestion("site", None, None, "not_found", [f"No site in the reference data is close to '{printed}'."])
    reasons = [f"Site name differs: invoice says '{printed}', closest is '{site['name']}'."]
    if evidence:
        reasons.append("Supporting evidence: " + " and ".join(evidence) + ".")
    return Suggestion("site", site["id"], site["name"], level, reasons)


# Cross-checks

def site_link_warning(study_id: int, site_id: int, data: ReferenceData) -> str | None:
    """A warning when the reference data doesn't list the site as taking part in the study."""
    if any(link["study_id"] == study_id and link["site_id"] == site_id for link in data.study_sites):
        return None
    study, site = _by_id(data.studies, study_id), _by_id(data.sites, site_id)
    if not study or not site:
        return None
    return f"{site['name']} isn't listed as taking part in {study['name']}."


def suggest(header: ExtractedHeader, data: ReferenceData) -> list[Suggestion]:
    sponsor = _suggest_sponsor(header, data)
    study = _suggest_study(header, data)
    site = _suggest_site(header, data)

    if study.entity_id is not None:
        study_record = _by_id(data.studies, study.entity_id)
        owner = _by_id(data.sponsors, study_record["sponsor_id"])
        if sponsor.entity_id is None:
            # Never more certain than the study it came from.
            level = LEVELS[min(LEVELS.index("likely"), LEVELS.index(study.confidence))]
            sponsor = Suggestion("sponsor", owner["id"], owner["name"], level,
                                 sponsor.reasons + ["Sponsor taken from the matched study."])
        elif sponsor.entity_id != owner["id"]:
            study.reasons.append(f"{study_record['name']} belongs to {owner['name']}, not {sponsor.entity_name}.")

    if study.entity_id is not None and site.entity_id is not None:
        warning = site_link_warning(study.entity_id, site.entity_id, data)
        if warning:
            site.confidence = lower_one_level(site.confidence)
            site.reasons.append(warning)

    return [sponsor, study, site]
