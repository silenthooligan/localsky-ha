"""Shared fixtures."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/localsky in the test harness."""
    yield


# Keep this at or above the compatibility floor (MIN_SERVICE_VERSION /
# MIN_API_VERSION in const.py, 0.7.0 / 1.12.0 as of the portfolio-parity bump)
# so the pairing paths pass the version gate. INFO_TOO_OLD below deliberately
# drops under the floor to exercise the rejection path.
INFO_OPEN = {
    "service": "localsky",
    "service_version": "0.7.0",
    "api_version": "1.13.0",
    "api_prefix": "/api/v1",
    "auth_required": False,
    "uuid": "11111111-2222-4333-8444-555555555555",
}

INFO_AUTH = {**INFO_OPEN, "auth_required": True}

INFO_TOO_OLD = {**INFO_OPEN, "service_version": "0.1.0"}
