"""Regression checks for the canonical, coordinated API surface."""

from main import app


def test_erp_ingestion_uses_only_canonical_bulk_routes():
    paths = app.openapi()["paths"]

    assert "/api/v1/integrations/erp/attendance/records" not in paths
    assert "/api/v1/integrations/erp/leaves/balances" not in paths
    assert "/api/v1/integrations/erp/attendance/records/bulk" in paths
    assert "/api/v1/integrations/erp/leaves/balances/bulk" in paths


def test_erp_master_data_has_one_write_route_per_external_identity():
    paths = app.openapi()["paths"]
    prefix = "/api/v1/integrations/erp"
    upserts = (
        "/organization/{erp_id}",
        "/units/by-erp-id/{erp_id}",
        "/departments/by-erp-id/{erp_id}",
        "/designations/by-erp-id/{erp_id}",
        "/employees/by-erp-id/{erp_id}",
        "/shifts/by-erp-id/{erp_id}",
    )
    for path in upserts:
        assert set(paths[prefix + path]) == {"put"}

    for path in ("/units", "/departments", "/designations", "/employees", "/shifts"):
        assert prefix + path not in paths
    for path in (
        "/units/{unit_id}",
        "/departments/{department_id}",
        "/designations/{designation_id}",
        "/employees/{employee_id}",
        "/shifts/{shift_id}",
    ):
        assert prefix + path not in paths

    retained = (
        "/employees/{employee_id}/deactivate",
        "/employees/{employee_id}/activate",
        "/employees/{employee_id}/password-reset",
        "/shifts/assignments",
        "/shifts/assignments/bulk",
        "/shifts/assignments/{assignment_id}/cancel",
        "/leaves/periods",
        "/leaves/types",
        "/leaves/types/{type_id}",
    )
    assert all(prefix + path in paths for path in retained)
    assert "/api/v1/auth/integrations/erp/employees/{employee_id}/password-reset" not in paths
    assert len([path for path in paths if path.startswith(prefix)]) == 21


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
