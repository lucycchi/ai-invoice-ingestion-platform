import json
import math
from pathlib import Path

import httpx
import pytest

from app.clients.reference_api import (
    ReferenceClient,
    ReferenceNotFound,
    ReferenceUnavailable,
    load_reference_data,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reference"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def capped_server(cap: int, seen: list[httpx.Request]):
    """A stand-in reference API serving the recorded data, never more than `cap` items per page."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path.removeprefix("/api/v1/")
        params = request.url.params
        if path == "catalog-items":
            items = _load(f"catalog-{params['sponsor_id']}-{params['study_id']}.json")
        elif "/" in path:
            kind, item_id = path.split("/")
            match = [i for i in _load(f"{kind}.json") if i["id"] == int(item_id)]
            return httpx.Response(200, json=match[0]) if match else httpx.Response(404, json={"detail": "Not found"})
        else:
            items = _load(f"{path}.json")
        size = min(int(params.get("page_size", 50)), cap)
        page = int(params.get("page", 1))
        pages = max(1, math.ceil(len(items) / size))
        chunk = items[(page - 1) * size : page * size]
        return httpx.Response(200, json={"items": chunk, "total": len(items), "page": page, "page_size": size, "pages": pages})

    return handler


def _client(handler) -> ReferenceClient:
    return ReferenceClient("http://api:8000", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_catalog_uses_page_size_200_and_gets_all():
    seen: list[httpx.Request] = []
    items = _client(capped_server(50, seen)).list_catalog(1, 1)
    assert len(items) == 100
    assert len(seen) == 2
    assert all(r.url.params["page_size"] == "200" for r in seen)


def test_lists_use_page_size_100():
    seen: list[httpx.Request] = []
    sites = _client(capped_server(100, seen)).list_sites()
    assert len(sites) == 8
    assert all(r.url.params["page_size"] == "100" for r in seen)


def test_unreachable():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ReferenceUnavailable) as err:
        _client(handler).list_sponsors()
    assert "http://api:8000" in str(err.value)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(ReferenceUnavailable):
        _client(handler).list_sponsors()
    assert ReferenceClient("http://api:8000").timeout == 10.0


def test_server_error_is_unavailable():
    with pytest.raises(ReferenceUnavailable):
        _client(lambda request: httpx.Response(500)).list_sites()


def test_not_found():
    with pytest.raises(ReferenceNotFound) as err:
        _client(capped_server(100, [])).get_site(99)
    assert (err.value.kind, err.value.id) == ("site", 99)


def test_get_one():
    assert _client(capped_server(100, [])).get_study(2)["name"] == "VERITAS"


def test_load_reference_data():
    data = load_reference_data(_client(capped_server(100, [])))
    assert (len(data.sponsors), len(data.studies), len(data.sites), len(data.study_sites)) == (4, 6, 8, 17)


@pytest.mark.parametrize("status", [400, 422])
def test_client_error_on_list_is_unavailable(status):
    with pytest.raises(ReferenceUnavailable) as err:
        _client(lambda request: httpx.Response(status, json={"detail": "bad"})).list_sites()
    assert "http://api:8000" in str(err.value)


def test_client_error_on_single_record_is_unavailable():
    with pytest.raises(ReferenceUnavailable):
        _client(lambda request: httpx.Response(400, json={"detail": "bad"})).get_site(1)


def test_non_json_answer_is_unavailable():
    with pytest.raises(ReferenceUnavailable):
        _client(lambda request: httpx.Response(200, text="<html>proxy error</html>")).list_sites()
