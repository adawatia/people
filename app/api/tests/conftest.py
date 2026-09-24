"""Never let the regression suite write to the application's configured staging DB."""
import os

import pytest
from sqlalchemy.engine import make_url


def pytest_sessionstart(session):
    url = os.environ.get("DATABASE_URL", "")
    if not url or not make_url(url).drivername.startswith("postgresql") or not (make_url(url).database or "").endswith("_test"):
        raise pytest.UsageError("Set DATABASE_URL explicitly to an isolated PostgreSQL database ending in _test.")
