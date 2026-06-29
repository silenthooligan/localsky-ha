"""Constants for the LocalSky integration."""
from __future__ import annotations

DOMAIN = "localsky"

# Config-flow keys.
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_HTTPS = "use_https"
CONF_API_TOKEN = "api_token"

# Options-flow keys.
OPT_USE_SSE = "use_sse"
OPT_POLL_INTERVAL = "poll_interval_seconds"
OPT_DEFAULT_RUN_SECONDS = "default_run_seconds"

# Defaults.
DEFAULT_PORT = 8090
DEFAULT_USE_HTTPS = False
DEFAULT_USE_SSE = True
# Polling cadence used as a fallback when SSE is unavailable or
# explicitly disabled in options. LocalSky's snapshots update every ~3s
# (tempest) / ~10s (irrigation); 30s polling is the sweet spot.
DEFAULT_POLL_INTERVAL = 30
DEFAULT_RUN_SECONDS = 600  # 10 min — matches LocalSky dashboard quick-run

# Minimum LocalSky service + API contract this integration actually requires.
# Checked against /api/v1/info at pairing time; an instance below the floor is
# refused with a clear "too old" error rather than paired into broken behavior.
#
# The floor tracks the real contract dependencies, not the oldest LocalSky that
# ever existed:
#   - api 1.6.0  added auth_required + the /api/v1/auth family the config flow
#     drives, and the stable `uuid` used for identity.
#   - api 1.7.0  retired the run_sequence_now action (410 Gone).
#   - api 1.12.0 added the sticky override actions (set_global_override /
#     set_zone_override) and the IrrigationSnapshot.global_override field that
#     the override service + select read. This is the binding floor.
# service 0.7.0 is the release line that carries api 1.12.0+.
MIN_SERVICE_VERSION = "0.7.0"
MIN_API_VERSION = "1.12.0"

# Canonical API prefix on the LocalSky instance. Some deployments
# mount both /api/* (legacy) and /api/v1/* (canonical with /info).
# New HACS installs target /api/v1.
API_PREFIX = "/api/v1"

# Service-action `kind` values dispatched to /api/v1/irrigation/action.
# These match the tagged-enum `Action` in localsky/src/api/irrigation.rs.
ACTION_RUN = "run"
ACTION_STOP = "stop"
ACTION_STOP_ALL = "stop_all"
ACTION_SET_PAUSE_UNTIL = "set_pause_until"
ACTION_CLEAR_PAUSE_UNTIL = "clear_pause_until"
ACTION_SET_THRESHOLD = "set_threshold"
ACTION_TOGGLE = "toggle"
ACTION_SET_OVERRIDE_TOMORROW = "set_override_tomorrow"
# Sticky overrides (LocalSky-native; persist until changed). A zone override
# beats the global one; "auto" clears it back to the engine verdict. Dispatched
# by the set_override / set_zone_override services.
ACTION_SET_GLOBAL_OVERRIDE = "set_global_override"
ACTION_SET_ZONE_OVERRIDE = "set_zone_override"

# Threshold slider keys understood by LocalSky's SetThreshold action.
THRESHOLD_KEYS = ("max_wind_mph", "min_temp_f", "rain_skip_in")

# Per-threshold UI hints — (min, max, step, unit).
THRESHOLD_LIMITS: dict[str, tuple[float, float, float, str | None]] = {
    "max_wind_mph": (0.0, 50.0, 1.0, "mph"),
    "min_temp_f": (20.0, 60.0, 1.0, "°F"),
    "rain_skip_in": (0.0, 1.0, 0.05, "in"),
}

# Permitted slugs for irrigation_override_tomorrow.
OVERRIDE_OPTIONS = ("none", "skip", "run")

# Permitted modes for the sticky global/per-zone override actions. "auto"
# follows the engine verdict, "skip" force-skips, "run" forces watering past
# the skip conditions. Mirrors the allow-list in the core's
# SetGlobalOverride / SetZoneOverride dispatch.
STICKY_OVERRIDE_MODES = ("auto", "skip", "run")
