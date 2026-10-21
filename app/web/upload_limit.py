"""Refusing an oversized upload while it arrives, before any of it is written to temporary storage."""

from starlette.responses import HTMLResponse

from app.uploads import MAX_FILE_BYTES

# Room for the form's own fields and boundaries around a file of the largest allowed size; the
# upload handler still checks the file itself against the exact limit.
UPLOAD_BODY_LIMIT = MAX_FILE_BYTES + 64 * 1024


def _too_large_page() -> str:
    from app.web.routes import templates  # the app's own layout, loaded when first needed

    return templates.get_template("too_large.html").render()


class _TooLarge(Exception):
    pass


class UploadSizeLimit:
    """Wraps the app: a POST to /invoices over the limit gets a 413 instead of being parsed."""

    def __init__(self, app, limit: int = UPLOAD_BODY_LIMIT):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/invoices":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            return await HTMLResponse(_too_large_page(), status_code=413)(scope, receive, send)

        received = 0
        over = False

        async def counted():
            nonlocal received, over
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.limit:
                over = True
                raise _TooLarge
            return message

        async def held(message):
            if not over:  # whatever the app answers after the cut-off is replaced by the 413
                await send(message)

        try:
            await self.app(scope, counted, held)
        except Exception:
            if not over:
                raise
        if over:
            await HTMLResponse(_too_large_page(), status_code=413)(scope, receive, send)
