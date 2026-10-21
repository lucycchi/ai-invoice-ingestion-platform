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


class FakeClaude:
    """Stands in for ClaudeClient. Answers come from the test; every call is logged with its timing.

    `extraction` is an ExtractionAnswer or an exception to raise; `match` is a function from
    (call number, list of line dicts) to a GroupAnswer or an exception; `fail_first` makes that many
    calls raise ClaudeFailed before answering.
    """

    def __init__(self, extraction=None, match=None, shared_tokens=100, delay=0.0):
        import threading

        self.model = "claude-opus-5-5"
        self.extraction = extraction
        self.match = match
        self.shared_tokens = shared_tokens
        self.delay = delay
        self.calls: list[dict] = []
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def _log(self, kind, **details):
        import time

        entry = {"kind": kind, "start": time.monotonic(), **details}
        with self._lock:
            self.calls.append(entry)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if self.delay:
            time.sleep(self.delay)
        return entry

    def _done(self, entry):
        import time

        entry["end"] = time.monotonic()
        with self._lock:
            self.in_flight -= 1

    def extract(self, data, media_type):
        from app.clients.claude import Usage

        entry = self._log("extract", media_type=media_type)
        try:
            if isinstance(self.extraction, Exception):
                raise self.extraction
            return self.extraction, Usage(requests=1, input_tokens=1500, output_tokens=400)
        finally:
            self._done(entry)

    def count_shared_tokens(self, shared):
        self.calls.append({"kind": "count", "start": 0.0, "end": 0.0})
        return self.shared_tokens

    def match_group(self, shared, lines):
        from app.clients.claude import Usage

        number = sum(1 for c in self.calls if c["kind"] == "match")
        entry = self._log("match", positions=[line["position"] for line in lines])
        try:
            answer = self.match(number, lines)
            if isinstance(answer, Exception):
                raise answer
            return answer, Usage(requests=1, input_tokens=2000, output_tokens=300)
        finally:
            self._done(entry)
