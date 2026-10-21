"""ERP HMAC authentication: signature, freshness, replay, scopes, outages.

These are unit tests of ``authenticate_erp_client`` against a synthetic ASGI
request, so they do not need the app database. The nonce store is the real
implementation (in memory), and audit writes are stubbed out.
"""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core import erp_auth
from core.erp_nonce_store import NonceStore

CLIENT_ID = "erp-test-client"
SECRET = "s" * 48
PATH = "/api/v1/integrations/erp/attendance/records/bulk"


def _settings(**overrides):
    base = {
        "is_development": False,
        "erp_api_key": "",
        "erp_api_clients": json.dumps({CLIENT_ID: {"secret": SECRET, "scopes": ["attendance:write"]}}),
        "erp_signature_max_age_seconds": 300,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _request(body: bytes, *, method="POST", path=PATH, query=b"", headers=None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "state": {},
    }
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _headers(*, ts, nonce, signature, client=CLIENT_ID):
    return [
        (b"x-erp-client-id", client.encode()),
        (b"x-erp-timestamp", str(ts).encode()),
        (b"x-erp-nonce", nonce.encode()),
        (b"x-erp-signature", signature.encode()),
    ]


def _sign(*, method, target, ts, nonce, body, secret=SECRET):
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{method}\n{target}\n{ts}\n{nonce}\n{body_hash}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _signed_request(body: bytes = b'{"records": []}', *, ts=None, nonce=None, method="POST", target=PATH):
    ts = ts or int(time.time())
    nonce = nonce or uuid.uuid4().hex
    split = urlsplit(target)
    signature = _sign(method=method, target=target, ts=ts, nonce=nonce, body=body)
    request = _request(body, method=method, path=split.path, query=split.query.encode())
    return request, {"timestamp": str(ts), "nonce": nonce, "signature": signature}


@pytest.fixture(autouse=True)
def _patched_auth(monkeypatch):
    store = NonceStore()
    monkeypatch.setattr(erp_auth, "get_settings", lambda: _settings())
    monkeypatch.setattr(erp_auth, "get_global_nonce_store", lambda: store)
    monkeypatch.setattr(erp_auth, "record_audit_event", AsyncMock())
    return store


async def _authenticate(request, headers):
    return await erp_auth.authenticate_erp_client(
        request,
        legacy_key=None,
        client_id=CLIENT_ID,
        timestamp=headers["timestamp"],
        nonce=headers["nonce"],
        signature=headers["signature"],
        session=None,
    )


@pytest.mark.asyncio
async def test_valid_signature_returns_the_client_scopes():
    request, headers = _signed_request()
    principal = await _authenticate(request, headers)
    assert principal.client_id == CLIENT_ID
    assert "attendance:write" in principal.scopes


@pytest.mark.asyncio
async def test_tampered_body_is_rejected():
    request, headers = _signed_request(b'{"records": [1]}')
    tampered = _request(b'{"records": [2]}')
    with pytest.raises(HTTPException) as exc:
        await _authenticate(tampered, headers)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_query_string_is_part_of_the_signature():
    _, headers = _signed_request(ts=int(time.time()), target=f"{PATH}?limit=5")
    # Same signature, different query: canonicalisation must reject it.
    altered = _request(b'{"records": []}', query=b"limit=6")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(altered, headers)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_signature_with_the_wrong_secret_is_rejected():
    request, headers = _signed_request()
    bad = dict(headers)
    bad["signature"] = _sign(
        method="POST", target=PATH, ts=headers["timestamp"], nonce=headers["nonce"],
        body=b'{"records": []}', secret="w" * 48,
    )
    with pytest.raises(HTTPException) as exc:
        await _authenticate(request, bad)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_stale_timestamp_is_rejected():
    request, headers = _signed_request(ts=int(time.time()) - 900)
    with pytest.raises(HTTPException) as exc:
        await _authenticate(request, headers)
    assert exc.value.status_code == 403
    assert "timestamp" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_replayed_nonce_is_rejected_with_409():
    request, headers = _signed_request()
    await _authenticate(request, headers)
    replay_request, _ = _signed_request(ts=int(headers["timestamp"]), nonce=headers["nonce"])
    with pytest.raises(HTTPException) as exc:
        await _authenticate(replay_request, headers)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_replay_only_one_request_wins():
    request, headers = _signed_request()
    second_request, _ = _signed_request(ts=int(headers["timestamp"]), nonce=headers["nonce"])

    async def attempt(req):
        try:
            await _authenticate(req, headers)
            return "ok"
        except HTTPException as exc:
            return exc.status_code

    results = await asyncio.gather(attempt(request), attempt(second_request))
    assert results.count("ok") == 1
    assert results.count(409) == 1


@pytest.mark.asyncio
async def test_unknown_client_is_rejected():
    request, headers = _signed_request()
    with pytest.raises(HTTPException) as exc:
        await erp_auth.authenticate_erp_client(
            request,
            legacy_key=None,
            client_id="unknown-client",
            timestamp=headers["timestamp"],
            nonce=headers["nonce"],
            signature=headers["signature"],
            session=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_scope_is_rejected_even_with_a_valid_signature():
    request, headers = _signed_request()
    principal = await _authenticate(request, headers)
    dependency = erp_auth.require_erp_scope("employees:write")
    with pytest.raises(HTTPException) as exc:
        await dependency(principal)
    assert exc.value.status_code == 403
    assert "scope" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_unavailable_shared_nonce_store_fails_closed_in_production(_patched_auth):
    # Simulate production with no Redis: consumption must raise, and the request
    # must not be accepted as if it were a fresh nonce.
    _patched_auth.configure_production(redis=None)
    request, headers = _signed_request()
    with pytest.raises(HTTPException) as exc:
        await _authenticate(request, headers)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_short_client_secret_is_rejected(monkeypatch):
    request, headers = _signed_request()
    monkeypatch.setattr(
        erp_auth,
        "get_settings",
        lambda: _settings(
            erp_api_clients=json.dumps({CLIENT_ID: {"secret": "short", "scopes": ["attendance:write"]}})
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await _authenticate(request, headers)
    assert exc.value.status_code == 403
