from main import app

EXPECTED_SORT_FIELDS = {
    "/api/v1/audit": {"created_at", "action", "entity_type", "id"},
    "/api/v1/attendance/": {"attendance_date", "status", "id"},
    "/api/v1/attendance/checkins": {"punch_time", "punch_type", "source", "is_processed", "id"},
    "/api/v1/attendance/corrections": {"requested_at", "status", "id"},
    "/api/v1/dashboard/owner/exceptions": {"employee_code", "name", "unit_id", "department_id", "id"},
    "/api/v1/designations/": {"name", "id"},
    "/api/v1/employees/": {"employee_code", "name", "created_at", "status"},
    "/api/v1/employees/{emp_id}/work-history": {"from_date", "to_date", "created_at", "id"},
    "/api/v1/holidays/lists": {"name", "id"},
    "/api/v1/leaves/": {"applied_at", "status", "id"},
    "/api/v1/leaves/periods": {"name", "id"},
    "/api/v1/leaves/types": {"name", "id"},
    "/api/v1/notifications": {"created_at", "id"},
    "/api/v1/org/departments": {"name", "id"},
    "/api/v1/org/units": {"name", "id"},
    "/api/v1/overtime/": {"attendance_date", "status", "id"},
    "/api/v1/reports/attendance-matrix": {"employee_code", "name"},
    "/api/v1/reports/leave-summary": {"employee_code", "name"},
    "/api/v1/shifts/": {"name", "code", "start_time", "id"},
    "/api/v1/shifts/assignments": {"effective_from", "status"},
    "/api/v1/users/admin/accounts": {"username", "email", "created_at", "is_active", "id"},
    "/api/v1/work-arrangements/": {"created_at", "status", "id"},
}


def _sort_enum(parameter: dict, components: dict) -> set[str]:
    def find_choices(schema: dict) -> list[str] | None:
        if "enum" in schema:
            return schema["enum"]
        if "$ref" in schema:
            return find_choices(components[schema["$ref"].rsplit("/", 1)[-1]])
        return next((choices for branch in schema.get("anyOf", []) if (choices := find_choices(branch))), None)

    choices = find_choices(parameter["schema"])
    assert choices is not None, "sort_by must publish its accepted values as an OpenAPI enum"
    return set(choices)


def test_every_sort_parameter_publishes_its_repository_allowlist():
    schema = app.openapi()
    components = schema["components"]["schemas"]
    documented = {}
    for path, path_item in schema["paths"].items():
        operation = path_item.get("get")
        if operation is None:
            continue
        parameter = next((item for item in operation.get("parameters", []) if item["name"] == "sort_by"), None)
        if parameter is not None:
            documented[path] = _sort_enum(parameter, components)

    assert documented == EXPECTED_SORT_FIELDS
