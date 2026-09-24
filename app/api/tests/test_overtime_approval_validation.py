from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from schemas.overtime import OvertimeApprovalCreate, OvertimeRejectionCreate
from services.overtime_service import OvertimeService


@pytest.mark.asyncio
async def test_approval_cannot_exceed_calculated_minutes():
    record = SimpleNamespace(id=8, status="PENDING", calculated_minutes=45, employee_id=14)
    service = OvertimeService(AsyncMock())
    service.repo = SimpleNamespace(get_by_id_for_update=AsyncMock(return_value=record))

    with pytest.raises(HTTPException) as exc_info:
        await service.approve_overtime(8, OvertimeApprovalCreate(approved_minutes=46), actioned_by_user_id=22)

    assert exc_info.value.status_code == 422
    assert record.status == "PENDING"
    service.repo.get_by_id_for_update.assert_awaited_once_with(8)


def test_overtime_approval_payload_rejects_negative_minutes():
    with pytest.raises(ValidationError):
        OvertimeApprovalCreate(approved_minutes=-1)

    with pytest.raises(ValidationError):
        OvertimeApprovalCreate(approved_minutes=0)


def test_overtime_rejection_requires_a_reason():
    with pytest.raises(ValidationError):
        OvertimeRejectionCreate(remarks="   ")
