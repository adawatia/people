"""Never let the regression suite write to the application's configured staging DB."""

import os

import pytest
from sqlalchemy.engine import make_url

# Every test runs on its own event loop, so a pooled asyncpg connection would
# outlive it and fail on reuse. This must be set before the application imports
# its settings, which is why it lives at module import rather than in a fixture.
os.environ.setdefault("DB_DISABLE_POOL", "true")


def pytest_sessionstart(session):
    """Refuse to run unless the resolved database is an isolated ``*_test`` one.

    An explicit ``DATABASE_URL`` environment variable always wins, but when it is
    absent the project's own configuration is used, so a developer whose
    ``.env`` already points at a ``*_test`` database does not have to export the
    variable as well.  The safety property is unchanged: whatever the source, the
    suite only ever runs against a PostgreSQL database whose name ends in
    ``_test``.
    """
    environment_url = os.environ.get("DATABASE_URL", "").strip()
    if environment_url:
        url = environment_url
    else:
        from core.settings import get_settings

        url = get_settings().resolved_database_url_sync().strip()

    try:
        parsed = make_url(url)
    except Exception as exc:  # pragma: no cover - configuration error path
        raise pytest.UsageError(f"DATABASE_URL is not a valid SQLAlchemy URL: {exc}") from exc

    if not parsed.drivername.startswith("postgresql") or not (parsed.database or "").endswith("_test"):
        raise pytest.UsageError("Set DATABASE_URL explicitly to an isolated PostgreSQL database ending in _test.")
