"""Scoped, replay-protected authentication for ERP integration clients.

Nonce replay protection is provided by ``core.erp_nonce_store``.  In production
that module uses a shared Redis client (SET NX EX) so a signed request can be
accepted exactly once across every API worker.  In development or when no Redis
is configured it falls back to a process-local memory store.

Production failure mode: if Redis is unavailable the nonce store raises
``NonceStoreError``, which is mapped to 503 here so a transient Redis outage
does not silently allow replays."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import record_audit_event
from core.database import get_async_session
from core.erp_nonce_store import NonceStoreError, get_global_nonce_store
from core.settings import get_settings


@dataclass(frozen=True)
class ErpPrincipal:
    client_id: str
    scopes: frozenset[str]


def _clients() -> dict[str, dict]:
    raw = get_settings().erp_api_clients.strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ERP_API_CLIENTS must be valid JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("ERP_API_CLIENTS must be a JSON object keyed by client id")
    return value


def _deny(detail: str = "Could not validate ERP credentials") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _nonce_consume_failure_status(reason: str) -> int:
    """Map a nonce-store failure to an HTTP status for the ERP auth layer.

    * A clean replay (nonce already used) → 409 so the caller can distinguish
      it from a bad signature.
    * A store outage or misconfiguration in production → 503 so operators see
      that the request was not authenticated rather than silently accepted.
    """
    if reason == "replay":
        return status.HTTP_409_CONFLICT
    return status.HTTP_503_SERVICE_UNAVAILABLE


async def authenticate_erp_client(
    request: Request,
    legacy_key: str | None = Header(None, alias="X-API-Key", description="Development-only compatibility key"),
    client_id: str | None = Header(None, alias="X-ERP-Client-ID"),
    timestamp: str | None = Header(None, alias="X-ERP-Timestamp", description="Unix timestamp in seconds"),
    nonce: str | None = Header(None, alias="X-ERP-Nonce", min_length=16, max_length=128),
    signature: str | None = Header(None, alias="X-ERP-Signature", description="Lowercase hex HMAC-SHA256"),
    session: AsyncSession = Depends(get_async_session),
) -> ErpPrincipal:
    settings = get_settings()
    if settings.is_development and settings.erp_api_key and legacy_key:
        if hmac.compare_digest(legacy_key, settings.erp_api_key):
            return ErpPrincipal(client_id="legacy-development", scopes=frozenset({"*"}))

    if not all((client_id, timestamp, nonce, signature)):
        raise _deny()
    if not 16 <= len(nonce) <= 128:
        raise _deny()
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise _deny() from exc
    if abs(int(time.time()) - sent_at) > settings.erp_signature_max_age_seconds:
        raise _deny("ERP request timestamp is outside the accepted window")

    config = _clients().get(client_id)
    if not isinstance(config, dict):
        raise _deny()
    secret = str(config.get("secret", ""))
    scopes = config.get("scopes", [])
    if len(secret) < 32 or not isinstance(scopes, list):
        raise _deny()

    body_hash = hashlib.sha256(await request.body()).hexdigest()
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    canonical = f"{request.method.upper()}\n{target}\n{timestamp}\n{nonce}\n{body_hash}"
    expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        raise _deny()
    store = get_global_nonce_store()
    try:
        consumed = await store.consume(client_id, nonce, settings.erp_signature_max_age_seconds)
    except NonceStoreError as exc:
        # Production store cannot operate: do not accept the request and do not
        # pretend it is a clean replay.
        raise HTTPException(
            status_code=_nonce_consume_failure_status("store_unavailable"),
            detail="ERP nonce store unavailable",
        ) from exc

    if not consumed:
        raise HTTPException(
            status_code=_nonce_consume_failure_status("replay"),
            detail="ERP request nonce was already used",
        )

    principal = ErpPrincipal(client_id=client_id, scopes=frozenset(str(scope) for scope in scopes))
    await record_audit_event(
        session,
        actor=None,
        action="ERP_REQUEST_AUTHENTICATED",
        entity_type="erp_client",
        entity_id=client_id,
        filters={"method": request.method, "path": request.url.path, "scopes": sorted(principal.scopes)},
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client else None,
    )
    return principal


def require_erp_scope(scope: str):
    async def dependency(principal: ErpPrincipal = Depends(authenticate_erp_client)) -> ErpPrincipal:
        if "*" not in principal.scopes and scope not in principal.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ERP client lacks the required scope")
        return principal

    return dependency


verify_erp_api_key = authenticate_erp_client
