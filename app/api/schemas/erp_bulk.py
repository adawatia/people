"""Request shapes for ERP bulk master-data upserts.

Responses use the shared ``core.erp_batch.ErpBatchResult`` envelope so every
bulk endpoint reports the same summary, per-item status, code and retryability.
"""

from pydantic import BaseModel, Field

from schemas.designations import DesignationUpdate
from schemas.org import DepartmentUpsert, UnitUpdate


class ErpUnitUpsertItem(UnitUpdate):
    """One unit in a bulk upsert, identified by its ERP id."""

    erp_id: str


class ErpUnitBulkUpsert(BaseModel):
    units: list[ErpUnitUpsertItem] = Field(..., min_length=1, max_length=1000)


class ErpDepartmentUpsertItem(DepartmentUpsert):
    """One department in a bulk upsert, identified by its ERP id.

    ``unit_id`` refers to the local unit id, so the referenced units must have
    been synced (via the unit upsert endpoints) before departments are sent.
    """

    erp_id: str


class ErpDepartmentBulkUpsert(BaseModel):
    departments: list[ErpDepartmentUpsertItem] = Field(..., min_length=1, max_length=1000)


class ErpDesignationUpsertItem(DesignationUpdate):
    """One designation in a bulk upsert, identified by its ERP id."""

    erp_id: str


class ErpDesignationBulkUpsert(BaseModel):
    designations: list[ErpDesignationUpsertItem] = Field(..., min_length=1, max_length=1000)
