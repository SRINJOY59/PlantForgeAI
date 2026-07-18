"""Response hardening for the gateway.

The gateway is a JSON/SSE/document API - it never serves the SPA's HTML - so
these headers cost nothing legitimate and shut off a row of default browser
behaviours we do not want:

  nosniff       a source served as text/plain can't be re-sniffed as HTML and
                run as script - the teeth behind serving uploads as text.
  frame denial  nobody frames the API to dress up a clickjacking attack. The
                document viewer renders from a blob: URL, not the API response,
                so this does not touch our own viewing.
  no referrer   a doc_id or token in a path never leaks out in a Referer header.
  CSP           an API response has no legitimate need to load anything; if one
                is ever coerced into being rendered, it can pull in nothing.

setdefault, not assignment: a handler that deliberately set its own value wins.
"""

from starlette.middleware.base import BaseHTTPMiddleware

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy":
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def cors_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]
