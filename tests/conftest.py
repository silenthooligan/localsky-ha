"""Shared fixtures."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/localsky in the test harness."""
    yield


INFO_OPEN = {
    "service": "localsky",
    "service_version": "0.2.0",
    "api_version": "1.6.0",
    "api_prefix": "/api/v1",
    "auth_required": False,
    "uuid": "11111111-2222-4333-8444-555555555555",
}

INFO_AUTH = {**INFO_OPEN, "auth_required": True}

INFO_TOO_OLD = {**INFO_OPEN, "service_version": "0.1.0"}
