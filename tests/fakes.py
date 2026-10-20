"""Test-only stand-ins for the outside services. The running app never uses these."""

import json
from collections import Counter
from pathlib import Path

from app.clients.reference_api import ReferenceData, ReferenceNotFound, ReferenceUnavailable

REFERENCE_FIXTURES = Path(__file__).parent / "fixtures" / "reference"


def _load(name: str) -> list[dict]:
    return json.loads((REFERENCE_FIXTURES / name).read_text())


class FakeReference:
    """Answers from the recorded reference API data. Set `down = True` to make every call fail."""

    def __init__(self):
        self.calls = Counter()
        self.down = False
        self.base_url = "http://api:8000"

    def _call(self, name: str):
        self.calls[name] += 1
        if self.down:
            raise ReferenceUnavailable(self.base_url, "ConnectError")

    def list_sponsors(self):
        self._call("list_sponsors")
        return _load("sponsors.json")

    def list_studies(self, sponsor_id=None):
        self._call("list_studies")
        return [s for s in _load("studies.json") if sponsor_id is None or s["sponsor_id"] == sponsor_id]

    def list_sites(self):
        self._call("list_sites")
        return _load("sites.json")

    def list_study_sites(self):
        self._call("list_study_sites")
        return _load("study-sites.json")

    def list_catalog(self, sponsor_id, study_id):
        self._call("list_catalog")
        path = REFERENCE_FIXTURES / f"catalog-{sponsor_id}-{study_id}.json"
        return json.loads(path.read_text()) if path.exists() else []

    def _one(self, file, kind, id):
        self._call(f"get_{kind}")
        for item in _load(file):
            if item["id"] == id:
                return item
        raise ReferenceNotFound(kind, id)

    def get_sponsor(self, id):
        return self._one("sponsors.json", "sponsor", id)

    def get_study(self, id):
        return self._one("studies.json", "study", id)

    def get_site(self, id):
        return self._one("sites.json", "site", id)


def reference_data() -> ReferenceData:
    return ReferenceData(_load("sponsors.json"), _load("studies.json"), _load("sites.json"), _load("study-sites.json"))
