"""Form posts from another website must be refused (cross-site request forgery)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeClaude, FakeReference
from tests.test_extraction_step import saved_extraction


@pytest.fixture
def client(settings):
    claude = FakeClaude(extraction=saved_extraction("simple_invoice"))
    with TestClient(create_app(settings, claude=claude, reference=FakeReference()), follow_redirects=False) as c:
        yield c


def test_cross_site_post_refused(client):
    response = client.post("/invoices/1/change-metadata", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_foreign_origin_refused(client):
    response = client.post("/invoices/1/change-metadata", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_same_origin_allowed(client):
    response = client.post(
        "/invoices/1/change-metadata", headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code != 403


def test_requests_without_browser_headers_allowed(client):
    # Tests and command-line tools send neither header; only browsers do, and browsers always send them.
    assert client.post("/invoices/1/change-metadata").status_code != 403


def test_reads_never_refused(client):
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_rebound_host_refused_even_for_reads(client):
    # DNS rebinding: a hostile name that resolves to this machine. Only localhost names are served.
    assert client.get("/", headers={"Host": "evil.example:8080"}).status_code == 400


def test_rebound_origin_matching_host_refused(client):
    response = client.post(
        "/invoices/1/change-metadata",
        headers={"Host": "evil.example:8080", "Origin": "http://evil.example:8080", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code in (400, 403)


def test_localhost_names_allowed(client):
    for host in ("localhost:8080", "127.0.0.1:8080"):
        assert client.get("/", headers={"Host": host}).status_code == 200
        response = client.post("/invoices/1/change-metadata", headers={"Host": host, "Origin": f"http://{host}"})
        assert response.status_code != 403


def test_other_local_port_refused(client):
    response = client.post(
        "/invoices/1/change-metadata", headers={"Host": "localhost:8080", "Origin": "http://localhost:3000"}
    )
    assert response.status_code == 403
