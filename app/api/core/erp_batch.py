"""One response contract for every ERP bulk endpoint.

The ERP needs three things from a bulk write that a bare HTTP status cannot give
it: a correlation id it can quote in a support ticket, a per-item outcome, and a
machine-readable reason that says whether retrying the item is safe.  This module
owns all three so the endpoints cannot drift apart again.

Rules enforced here:

* An item is reported ``accepted`` only after the caller's persistence step and
  the enclosing savepoint succeeded.
* Error text is always derived from a known, safe source (an ``HTTPException``
  detail or a fixed code). Driver messages, SQL, connection strings and stack
  traces are replaced with a generic message; the detail goes to the server log
  under the batch id instead.
* ``retryable`` distinguishes "try this item again" (transient persistence or
  server-side failure) from "fix the payload" (validation or conflict).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Literal

from fastapi import Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from core.erp_sync import error_text
from db.models import ErpSyncBatch, now_ist

logger = logging.getLogger("hrms.erp")

BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

ErpItemStatus = Literal["accepted", "duplicate", "failed"]


class ErpItemError(Exception):
    """A deliberate, ERP-safe per-item rejection.

    Raise this instead of a bare ``ValueError`` when the reason is meaningful to
    the caller: the code and message are returned verbatim, and ``retryable``
    tells the ERP whether resending the same item can succeed.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ErpItemResult(BaseModel):
    key: str
    status: ErpItemStatus
    id: int | None = None
    code: str | None = None
    message: str | None = None
    retryable: bool = False


class ErpBatchResult(BaseModel):
    """Summary plus item-level results for one bulk request."""

    batch_id: str
    endpoint: str
    received_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0
    retryable_failed_count: int = 0
    items: list[ErpItemResult] = Field(default_factory=list)

    def add_accepted(self, key: str, item_id: int | None = None) -> None:
        self.items.append(ErpItemResult(key=key, status="accepted", id=item_id))
        self.accepted_count += 1

    def add_duplicate(self, key: str, item_id: int | None = None, message: str | None = None) -> None:
        self.items.append(ErpItemResult(key=key, status="duplicate", id=item_id, message=message))
        self.duplicate_count += 1

    def add_failure(
        self,
        key: str,
        exc: BaseException | None = None,
        *,
        code: str | None = None,
        message: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        """Record one failed item, logging the unsanitised cause server-side."""
        if exc is not None:
            code, message, retryable = classify_erp_error(exc)
            log_erp_item_failure(key, exc, self.batch_id, self.endpoint)
        self.items.append(
            ErpItemResult(
                key=key,
                status="failed",
                code=code or "INTERNAL_ERROR",
                message=message or "Unexpected error while processing this record",
                retryable=bool(retryable),
            )
        )
        self.failed_count += 1
        if retryable:
            self.retryable_failed_count += 1

    def finalize(self) -> ErpBatchResult:
        """Recompute counters from the item list; safe to call more than once."""
        self.accepted_count = sum(1 for item in self.items if item.status == "accepted")
        self.duplicate_count = sum(1 for item in self.items if item.status == "duplicate")
        failed = [item for item in self.items if item.status == "failed"]
        self.failed_count = len(failed)
        self.retryable_failed_count = sum(1 for item in failed if item.retryable)
        return self


def resolve_batch_id(x_erp_batch_id: str | None = Header(None, alias="X-ERP-Batch-Id")) -> str:
    """Accept the ERP's correlation id, or mint one for this request.

    Echoing the caller's id makes a retry traceable: the ERP can resend the same
    page with the same id and the audit rows line up one-to-one.
    """
    if x_erp_batch_id is None:
        return uuid.uuid4().hex
    if not BATCH_ID_PATTERN.fullmatch(x_erp_batch_id):
        raise HTTPException(
            status_code=422,
            detail="X-ERP-Batch-Id must be 8-128 characters of letters, digits, '.', '_', ':' or '-'",
        )
    return x_erp_batch_id


def new_batch(endpoint: str, batch_id: str, received_count: int = 0) -> ErpBatchResult:
    return ErpBatchResult(batch_id=batch_id, endpoint=endpoint, received_count=received_count)


def apply_batch_status(response: Response, result: ErpBatchResult) -> None:
    """Echo the batch id and communicate whole-batch failure via HTTP status.

    A request that was understood but contained only transient failures is a
    503: the ERP should retry the same page with the same ``X-ERP-Batch-Id``.
    Item-level validation failures stay 200 - the request itself succeeded and
    retrying it unchanged would fail again.
    """
    result.finalize()
    response.headers["X-ERP-Batch-Id"] = result.batch_id
    if (
        result.received_count
        and result.failed_count == result.received_count
        and result.retryable_failed_count == result.failed_count
    ):
        response.status_code = 503
        response.headers["Retry-After"] = "30"


def classify_erp_error(exc: BaseException) -> tuple[str, str, bool]:
    """Map an exception to ``(code, safe_message, retryable)``.

    The message is written for the ERP client, not for a developer: it never
    contains driver text, SQL, identifiers beyond the ERP's own key, or a stack
    trace. The full exception is logged separately by ``log_erp_item_failure``.
    """
    if isinstance(exc, ErpItemError):
        return exc.code, exc.message, exc.retryable
    if isinstance(exc, HTTPException):
        return (
            _http_code(exc.status_code),
            error_text(exc.detail),
            exc.status_code >= 500,
        )
    if isinstance(exc, IntegrityError):
        return "CONFLICT", "Conflicts with existing data", False
    if isinstance(exc, (OperationalError, DBAPIError)):
        return (
            "TRANSIENT_PERSISTENCE_ERROR",
            "Temporarily unable to persist this record; retry later",
            True,
        )
    if isinstance(exc, TimeoutError):
        return "TRANSIENT_TIMEOUT", "Timed out while processing this record; retry later", True
    return "INTERNAL_ERROR", "Unexpected error while processing this record", True


def _http_code(status_code: int) -> str:
    return {
        400: "INVALID_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "REQUEST_REJECTED")


def log_erp_item_failure(key: str, exc: BaseException, batch_id: str, endpoint: str) -> None:
    """Log the real cause server-side; never returned to the ERP."""
    logger.warning(
        "ERP item rejected",
        extra={
            "erp_batch_id": batch_id,
            "erp_endpoint": endpoint,
            "erp_item_key": key,
            "error_class": type(exc).__name__,
        },
        exc_info=not isinstance(exc, (ErpItemError, HTTPException)),
    )


async def record_batch(
    session,
    result: ErpBatchResult,
    *,
    client_id: str | None,
    http_status: int = 200,
    status: str = "COMPLETED",
) -> None:
    """Persist the correlation row for this batch.

    Written in a savepoint: a failure to record the audit row must never roll
    back work the ERP was already told was accepted.
    """
    result.finalize()
    failed_codes = [item.code for item in result.items if item.status == "failed" and item.code]
    try:
        async with session.begin_nested():
            session.add(
                ErpSyncBatch(
                    batch_id=result.batch_id,
                    endpoint=result.endpoint,
                    client_id=client_id,
                    received_count=result.received_count,
                    accepted_count=result.accepted_count,
                    duplicate_count=result.duplicate_count,
                    failed_count=result.failed_count,
                    retryable_failed_count=result.retryable_failed_count,
                    status=status,
                    http_status=http_status,
                    last_error_code=failed_codes[0] if failed_codes else None,
                    finished_at=now_ist(),
                )
            )
            await session.flush()
    except Exception:  # pragma: no cover - audit best effort
        logger.exception("Could not record ERP batch audit row", extra={"erp_batch_id": result.batch_id})
