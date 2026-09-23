"""Guard the role/permission model against dead gates and duplicated grants.

A permission code that the API *enforces* but no role is ever *granted* can
never pass for any user, which silently turns an endpoint into a permanent
403.  That is how ``attendance.approve_correction`` disabled attendance
approvals for HR Admins and Super Admins alike.

The model is: ``BASE_EMPLOYEE_PERMISSIONS`` (implicit for every employee) plus
one bundle per elevated business role in ``ROLE_PERMISSIONS``.  Bundles must
not repeat base permissions.

These tests are static: they read the source tree, so they fail fast in CI
without a database and name the offending file for each dead gate.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = REPO_ROOT / "app" / "web"

# Source trees that enforce permissions / declare the role catalogue.
BACKEND_DIRS = [API_ROOT / "routers", API_ROOT / "core"]
AUTH_MODULE = API_ROOT / "core" / "auth.py"
RBAC_MODULE = API_ROOT / "core" / "rbac.py"

# Callable -> positional index of the permission argument.
PERMISSION_CALL_ARGS = {
    "require_permission": 0,
    "get_permission_scope": 1,
    "user_has_permission": 1,
    "require_employee_access": 2,
}


def _string(value: ast.expr | None) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _string_collection(value: ast.expr | None) -> list[str]:
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return [code for element in value.elts if (code := _string(element))]
    return []


def _location(path: Path, line: int) -> str:
    """Readable ``file:line`` label for a finding (also works outside the API tree)."""
    try:
        return f"{path.relative_to(API_ROOT)}:{line}"
    except ValueError:
        return f"{path}:{line}"


def _module_string_constants(tree: ast.Module) -> dict[str, list[str]]:
    """Map module-level names to the string collections they hold.

    Lets us resolve indirection such as ``require_employee_access(..., ATTENDANCE_READ_PERMISSIONS)``.
    """
    constants: dict[str, list[str]] = {}
    for node in tree.body:
        targets: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        codes = _string_collection(value) or ([code] if (code := _string(value)) else [])
        for name in targets:
            if codes:
                constants[name] = codes
    return constants


def _module_literal(tree: ast.Module, name: str) -> ast.expr | None:
    """Return the literal assigned to a module-level name, if any."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return node.value
    return None


def permission_bundles() -> tuple[set[str], dict[str, set[str]]]:
    """Parse ``BASE_EMPLOYEE_PERMISSIONS`` and ``ROLE_PERMISSIONS`` from core/auth.py."""
    tree = ast.parse(AUTH_MODULE.read_text(encoding="utf-8"))

    base_node = _module_literal(tree, "BASE_EMPLOYEE_PERMISSIONS")
    base = set(_string_collection(base_node))
    if not base:
        raise TypeError("BASE_EMPLOYEE_PERMISSIONS must be a non-empty set literal in core/auth.py")

    roles_node = _module_literal(tree, "ROLE_PERMISSIONS")
    if not isinstance(roles_node, ast.Dict):
        raise TypeError("ROLE_PERMISSIONS must be a dict literal in core/auth.py")
    roles: dict[str, set[str]] = {}
    for key, role_permissions in zip(roles_node.keys, roles_node.values, strict=True):
        role = _string(key)
        if role is None:
            continue
        roles[role] = set(_string_collection(role_permissions))
    return base, roles


def granted_permissions() -> dict[str, set[str]]:
    """Full effective set per role: base employee permissions + role bundle."""
    base, roles = permission_bundles()
    return {"EMPLOYEE": set(base), **{role: set(base) | codes for role, codes in roles.items()}}


def _looks_like_permission_code(value: str | None) -> bool:
    """Permission codes are dotted lowercase identifiers (``leave.approve``)."""
    return bool(value) and bool(re.fullmatch(r"[a-z_]+\.[a-z_]+", value))


def enforced_permissions() -> dict[str, set[str]]:
    """Collect every permission code the API enforces, mapped to where."""
    enforced: dict[str, set[str]] = {}
    for directory in BACKEND_DIRS:
        for path in sorted(directory.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            constants = _module_string_constants(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    # Membership checks such as ``"leave.approve" in user_perms``.
                    if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                        candidates = _string_collection(node.left) or [_string(node.left)]
                        for code in candidates:
                            if _looks_like_permission_code(code):
                                enforced.setdefault(code, set()).add(_location(path, node.lineno))
                    continue
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                index = PERMISSION_CALL_ARGS.get(node.func.id)
                if index is None or len(node.args) <= index:
                    continue
                argument = node.args[index]
                codes = _string_collection(argument) or ([code] if (code := _string(argument)) else [])
                if not codes and isinstance(argument, ast.Name):
                    codes = constants.get(argument.id, [])
                for code in codes:
                    enforced.setdefault(code, set()).add(_location(path, node.lineno))

    # Dashboard widget gates in core/rbac.py ({"key": ..., "permission": "..."}).
    rbac_tree = ast.parse(RBAC_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(rbac_tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if _string(key) == "permission" and (code := _string(value)):
                enforced.setdefault(code, set()).add(_location(RBAC_MODULE, node.lineno))
    return enforced


def web_reference_locations() -> dict[str, set[str]]:
    """Collect permission codes the web app gates UI on (hasPermission / nav arrays)."""
    references: dict[str, set[str]] = {}
    if not WEB_ROOT.exists():
        return references
    has_permission = re.compile(r"hasPermission\(\s*'([a-z_.]+)'\s*\)")
    nav_gate = re.compile(r"permissions:\s*\[([^\]]*)\]")
    quoted_code = re.compile(r"'([a-z_]+(?:\.[a-z_]+)+)'")
    for path in sorted(WEB_ROOT.rglob("*")):
        if path.suffix not in {".vue", ".ts"} or any(part in {".nuxt", "node_modules", "dist"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        codes = has_permission.findall(text)
        for group in nav_gate.findall(text):
            codes.extend(quoted_code.findall(group))
        for code in codes:
            references.setdefault(code, set()).add(str(path.relative_to(WEB_ROOT)))
    return references


def test_no_permission_is_enforced_without_being_granted():
    """Every enforced code must be reachable through at least one role."""
    granted = {code for codes in granted_permissions().values() for code in codes}
    offenders = {code: where for code, where in enforced_permissions().items() if code not in granted}
    assert not offenders, (
        "These permission codes are enforced but granted to no role in "
        f"FIXED_ROLE_PERMISSIONS, so the check can never pass: {offenders}"
    )


def test_every_elevated_role_adds_permissions_and_repeats_no_base_code():
    base, roles = permission_bundles()
    assert set(roles) == {"DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER"}
    for role, codes in roles.items():
        assert codes, f"{role} adds no permissions"
        duplicated = codes & base
        assert not duplicated, f"{role} repeats base employee permissions: {sorted(duplicated)}"


def test_fixed_role_permissions_matches_base_plus_bundles():
    """The compatibility role → permission view stays consistent with the model."""
    from core.auth import FIXED_ROLE_PERMISSIONS, effective_permissions

    base, roles = permission_bundles()
    assert FIXED_ROLE_PERMISSIONS["EMPLOYEE"] == effective_permissions(None) == base
    for role in roles:
        assert FIXED_ROLE_PERMISSIONS[role] == effective_permissions(role)
    assert set(FIXED_ROLE_PERMISSIONS) == {"EMPLOYEE", *roles}


def test_no_web_gate_references_an_ungranted_permission():
    """A UI gate on a code nobody holds hides that action from every user."""
    granted = {code for codes in granted_permissions().values() for code in codes}
    offenders = {code: where for code, where in web_reference_locations().items() if code not in granted}
    assert not offenders, (
        f"The web app gates UI on permission codes no role holds, so the UI can never unlock: {offenders}"
    )
