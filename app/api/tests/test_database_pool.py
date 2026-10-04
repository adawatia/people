"""Health probes share a pool instead of creating a pool per request."""

from core.database import get_engine


def test_health_engine_is_reused():
    first = get_engine()
    assert get_engine() is first
