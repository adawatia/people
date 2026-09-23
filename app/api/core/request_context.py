"""Request metadata used by authentication throttling and the security audit.

Keeping these three helpers in one place means every auth event records the same
shape of context, and the trust decision about proxy headers is made once.

``X-Forwarded-For`` is only honoured when ``TRUST_PROXY_HEADERS=true``.  Behind
this project's BFF the API peer address is the BFF, so a deployment that does not
forward the browser address ends up throttling the whole tenant as one IP; the
setting is therefore a deliberate deployment decision, not a default.  Never
enable it on an API that is directly reachable from the internet, where any
client could forge the header.
"""

from __future__ import annotations

from fastapi import Request

from core.settings import get_settings


def client_ip(request: Request | None) -> str | None:
    """Best-effort client address (proxy-aware only when explicitly trusted)."""
    if request is None:
        return None
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip() or None
    return request.client.host if request.client else None


def user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    value = request.headers.get("user-agent")
    return value[:255] if value else None


def request_id(request: Request | None) -> str | None:
    """Correlation id for this request.

    Prefers an id the caller supplied (gateway/BFF correlation), then the id the
    request-logging middleware minted, so an audit event is always traceable to
    the log line for the same request.
    """
    if request is None:
        return None
    value = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    if value:
        return value[:100]
    if request.state is not None:
        return getattr(request.state, "request_id", None)
    return None
