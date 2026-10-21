"""Refuse state-changing requests that a browser says came from another website.

The app has no login, so without this any web page the user visits could post a form to
localhost:8080 (cross-site request forgery). Browsers send Sec-Fetch-Site and Origin on such
requests; requests from tests or command-line tools send neither and are let through.
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
REFUSAL = "Refused: this request came from another website."


class CrossSiteGuard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS:
            if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
                return PlainTextResponse(REFUSAL, status_code=403)
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return PlainTextResponse(REFUSAL, status_code=403)
        return await call_next(request)
