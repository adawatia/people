"""Regression checks for the canonical, coordinated API surface."""

from main import app


def test_erp_ingestion_uses_only_canonical_bulk_routes():
    paths = app.openapi()["paths"]

    assert "/api/v1/integrations/erp/attendance/records" not in paths
    assert "/api/v1/integrations/erp/leaves/balances" not in paths
    assert "/api/v1/integrations/erp/attendance/records/bulk" in paths
    assert "/api/v1/integrations/erp/leaves/balances/bulk" in paths


def test_public_attendance_checkins_are_read_only():
    checkins = app.openapi()["paths"]["/api/v1/attendance/checkins"]
    assert set(checkins) == {"get"}
    assert "/api/v1/attendance/checkins/bulk" not in app.openapi()["paths"]


def test_erp_leave_master_data_is_under_the_integration_namespace():
    paths = app.openapi()["paths"]

    assert "/api/v1/leaves/periods" in paths
    assert set(paths["/api/v1/leaves/periods"]) == {"get"}
    assert "/api/v1/leaves/types" in paths
    assert set(paths["/api/v1/leaves/types"]) == {"get"}
    assert "/api/v1/integrations/erp/leaves/periods" in paths
    assert "/api/v1/integrations/erp/leaves/types" in paths
    assert "/api/v1/integrations/erp/leaves/types/{type_id}" in paths


def test_collection_contracts_publish_search_not_q():
    paths = app.openapi()["paths"]
    for path in ("/api/v1/employees/", "/api/v1/overtime/"):
        parameters = {item["name"] for item in paths[path]["get"]["parameters"]}
        assert "search" in parameters
        assert "q" not in parameters


def test_erp_bulk_and_feed_operations_have_explicit_response_schemas():
    paths = app.openapi()["paths"]
    operations = (
        paths["/api/v1/integrations/erp/attendance/records/bulk"]["post"],
        paths["/api/v1/integrations/erp/holidays/bulk"]["post"],
        paths["/api/v1/integrations/erp/overtime/records/bulk"]["post"],
        paths["/api/v1/integrations/erp/leaves/balances/bulk"]["post"],
        paths["/api/v1/integrations/erp/leaves/changes"]["get"],
        paths["/api/v1/integrations/erp/leaves/changes/ack"]["post"],
    )
    for operation in operations:
        assert "application/json" in operation["responses"]["200"]["content"]
