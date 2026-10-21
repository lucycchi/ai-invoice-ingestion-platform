"""The request-size guard: an oversized upload is refused before any of it is written to temporary storage."""

import asyncio

from app.web.upload_limit import UploadSizeLimit
from tests.test_upload import client  # noqa: F401  (a fixture)

LIMIT = 100


class Inner:
    """A stand-in app that reads the whole body, recording how much reached it."""

    def __init__(self):
        self.called = False
        self.received = 0

    async def __call__(self, scope, receive, send):
        self.called = True
        while True:
            message = await receive()
            self.received += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _call(app, chunks, headers=(), path="/invoices", method="POST"):
    scope = {"type": "http", "method": method, "path": path, "headers": list(headers)}
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    sent = []

    async def receive():
        return queue.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body.decode()


def test_declared_length_over_limit_never_reaches_the_app():
    inner = Inner()
    status, body = _call(UploadSizeLimit(inner, LIMIT), [b"x" * 10], headers=[(b"content-length", b"500")])
    assert status == 413 and "at most 10 MB" in body
    assert not inner.called


def test_streamed_body_over_limit_is_cut_off():
    inner = Inner()
    status, _ = _call(UploadSizeLimit(inner, LIMIT), [b"x" * 60] * 10)
    assert status == 413
    assert inner.received <= LIMIT


def test_body_within_limit_passes():
    inner = Inner()
    assert _call(UploadSizeLimit(inner, LIMIT), [b"x" * 60], headers=[(b"content-length", b"60")]) == (200, "ok")


def test_other_paths_not_limited():
    inner = Inner()
    assert _call(UploadSizeLimit(inner, LIMIT), [b"x" * 500], path="/invoices/1/confirm") == (200, "ok")


def test_app_refuses_oversized_upload(client):
    big = b"%PDF-" + b"x" * (11 * 1024 * 1024)
    response = client.post("/invoices", files={"file": ("big.pdf", big)})
    assert response.status_code == 413
    assert "at most 10 MB" in response.text
