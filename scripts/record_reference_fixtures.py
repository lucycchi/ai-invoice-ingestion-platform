"""Record the running reference API's answers as test fixtures.

Run from the project root while the reference API is up:
    .venv/bin/python scripts/record_reference_fixtures.py
Writes every list, and each sponsor and study catalog, to tests/fixtures/reference/.
"""

import json
from pathlib import Path

import httpx

BASE = "http://localhost:8000/api/v1"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "reference"


def fetch_all(client: httpx.Client, path: str, page_size: int, **params) -> list[dict]:
    items, page = [], 1
    while True:
        body = client.get(f"{BASE}/{path}", params={**params, "page": page, "page_size": page_size}).json()
        items += body["items"]
        if page >= body["pages"]:
            return items
        page += 1


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=10) as client:
        lists = {name: fetch_all(client, name, 100) for name in ("sponsors", "studies", "sites", "study-sites")}
        for name, items in lists.items():
            (OUT / f"{name}.json").write_text(json.dumps(items, indent=2) + "\n")
            print(f"{name}: {len(items)}")
        for study in lists["studies"]:
            items = fetch_all(client, "catalog-items", 200, sponsor_id=study["sponsor_id"], study_id=study["id"])
            name = f"catalog-{study['sponsor_id']}-{study['id']}.json"
            (OUT / name).write_text(json.dumps(items, indent=2) + "\n")
            print(f"{name}: {len(items)}")


if __name__ == "__main__":
    main()
