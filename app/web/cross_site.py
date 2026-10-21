"""Refuse state-changing requests that a browser says came from another website.

The app has no login, so without this any web page the user visits could post a form to
localhost:8080 (cross-site request forgery). Browsers send Sec-Fetch-Site and Origin on such
requests; requests from tests or command-line tools send neither and are let through.
"""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
REFUSAL = "Refused: this request came from another website."


class CrossSiteGuard(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: list[str]):
        super().__init__(app)
        self.allowed_hosts = set(allowed_hosts)

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS:
            if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
                return PlainTextResponse(REFUSAL, status_code=403)
            origin = request.headers.get("origin")
            # The Host header is trustworthy (TrustedHostMiddleware runs first), so the Origin must
            # match it exactly, port included, and name one of the app's own hosts.
            if origin and (urlsplit(origin).hostname not in self.allowed_hosts
                           or urlsplit(origin).netloc != request.headers.get("host")):
                return PlainTextResponse(REFUSAL, status_code=403)
        return await call_next(request)


def add_host_guards(app, allowed_hosts: list[str]) -> None:
    """Serve only the app's own host names, and refuse cross-site posts."""
    app.add_middleware(CrossSiteGuard, allowed_hosts=allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
