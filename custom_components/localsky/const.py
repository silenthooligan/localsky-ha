"""Constants for the LocalSky integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "localsky"

# Config-flow keys.
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_HTTPS = "use_https"

# Defaults.
DEFAULT_PORT = 8090
DEFAULT_USE_HTTPS = False

# Polling cadence. LocalSky's snapshots update every ~3 seconds for
# Tempest weather (faster than HA cares about) and every ~10 seconds
# for irrigation state. Polling every 30 seconds gives HA fresh data
# without hammering the LAN service.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# Minimum LocalSky service version the integration is built against.
# Used by /api/v1/info probe at setup time; we warn on lower versions
# but don't refuse.
MIN_SERVICE_VERSION = "0.2.0"
MIN_API_VERSION = "1.0.0"

# Canonical API prefix on the LocalSky instance.
API_PREFIX = "/api/v1"

# Service-action kinds dispatched to /api/v1/irrigation/action.
ACTION_RUN = "run"
ACTION_STOP = "stop"
ACTION_STOP_ALL = "stop_all"
ACTION_PAUSE = "pause"
ACTION_SKIP = "skip"
