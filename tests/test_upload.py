import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app.main import create_app
from app.models import Invoice
from tests.conftest import REPO_ROOT

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MB = 1024 * 1024


def _pdf(pages: int) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    for n in range(pages):
        c.drawString(100, 700, f"Page {n + 1}")
        c.showPage()
    c.save()
    return buffer.getvalue()


def _encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(_pdf(1))))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), follow_redirects=False) as c:
        yield c


def _upload(client, data: bytes, name: str):
    return client.post("/invoices", files={"file": (name, data)})


def _invoices(client) -> list[Invoice]:
    with client.app.state.sessions() as s:
        return s.query(Invoice).order_by(Invoice.id).all()


def test_rejects_text_named_pdf(client):
    response = _upload(client, b"hello", "fake.pdf")
    assert response.status_code == 415
    assert "PDF, PNG, JPEG or WebP" in response.text
    assert _invoices(client) == []


def test_rejects_over_10mb(client):
    response = _upload(client, b"%PDF-1.4\n" + b"0" * (10 * MB), "big.pdf")
    assert response.status_code == 413
    assert "10 MB" in response.text


def test_rejects_image_over_7mb(client):
    too_big = PNG_SIGNATURE + b"0" * (7 * MB + 1 - len(PNG_SIGNATURE))
    response = _upload(client, too_big, "big.png")
    assert response.status_code == 413
    assert "Images can be at most 7 MB" in response.text
    exactly_7mb = PNG_SIGNATURE + b"0" * (7 * MB - len(PNG_SIGNATURE))
    assert _upload(client, exactly_7mb, "ok.png").status_code == 303


def test_rejects_21_page_pdf(client):
    response = _upload(client, _pdf(21), "long.pdf")
    assert response.status_code == 413
    assert "20 pages" in response.text


@pytest.mark.parametrize(
    "data",
    [b"%PDF-1.4\n" + b"\x00garbage" * 50, b"", _encrypted_pdf()],
    ids=["corrupt", "empty", "encrypted"],
)
def test_rejects_corrupt_pdf(client, data):
    response = _upload(client, data, "bad.pdf")
    assert response.status_code in (415, 422)
    assert "couldn't" in response.text.lower() or "PDF, PNG, JPEG or WebP" in response.text
    assert _invoices(client) == []


def test_accepts_sample(client, settings):
    data = (REPO_ROOT / "sample-invoices" / "simple-invoice.pdf").read_bytes()
    response = _upload(client, data, "simple-invoice.pdf")
    assert response.status_code == 303
    assert response.headers["location"] == "/invoices/1"
    [invoice] = _invoices(client)
    assert invoice.status == "extracting"
    assert invoice.original_filename == "simple-invoice.pdf"
    assert invoice.media_type == "application/pdf"
    stored = settings.data_dir / "uploads" / invoice.stored_path
    assert invoice.stored_path != "simple-invoice.pdf"
    assert stored.read_bytes() == data


def test_list_newest_first(client):
    _upload(client, _pdf(1), "first.pdf")
    _upload(client, _pdf(1), "second.pdf")
    page = client.get("/").text
    assert page.index("second.pdf") < page.index("first.pdf")
    assert 'href="/invoices/1"' in page and 'href="/invoices/2"' in page
    assert "extracting" in page.lower() or "reading" in page.lower()


def test_escapes_file_name(client):
    _upload(client, _pdf(1), "<b>x</b>.pdf")
    page = client.get("/").text
    assert "&lt;b&gt;x&lt;/b&gt;.pdf" in page
    assert "<b>x</b>.pdf" not in page


def test_invoice_page_unknown(client):
    assert client.get("/invoices/99").status_code == 404


def test_rejects_several_files(client):
    response = client.post("/invoices", files=[("file", ("a.pdf", _pdf(1))), ("file", ("b.pdf", _pdf(1)))])
    assert response.status_code == 422
    assert "one file at a time" in response.text
    assert _invoices(client) == []


def test_accepts_restriction_only_pdf(client):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(_pdf(1))))
    writer.encrypt(user_password="", owner_password="owner-secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    assert _upload(client, buffer.getvalue(), "restricted.pdf").status_code == 303
