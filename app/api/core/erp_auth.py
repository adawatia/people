"""Scoped, replay-protected authentication for ERP integration clients."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import record_audit_event
from core.database import get_async_session
from core.settings import get_settings


@dataclass(frozen=True)
class ErpPrincipal:
    client_id: str
    scopes: frozenset[str]


_nonce_lock = asyncio.Lock()
_memory_nonces: dict[str, float] = {}


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


async def _consume_nonce(client_id: str, nonce: str, ttl_seconds: int) -> bool:
    settings = get_settings()
    key = f"hrms:erp:nonce:{client_id}:{nonce}"
    if settings.auth_throttle_backend == "redis":
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        try:
            return bool(await redis.set(key, "1", ex=ttl_seconds, nx=True))
        finally:
            await redis.aclose()

    now = time.monotonic()
    async with _nonce_lock:
        for saved_key, expires_at in list(_memory_nonces.items()):
            if expires_at <= now:
                del _memory_nonces[saved_key]
        if key in _memory_nonces:
            return False
        _memory_nonces[key] = now + ttl_seconds
        return True


def _deny(detail: str = "Could not validate ERP credentials") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


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
    if not await _consume_nonce(client_id, nonce, settings.erp_signature_max_age_seconds):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ERP request nonce was already used")

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
