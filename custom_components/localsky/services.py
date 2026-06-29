"""Integration-level service actions for LocalSky.

Seven user-facing actions:

- ``localsky.run_zone``        Run a single zone for N seconds.
- ``localsky.stop_zone``       Stop a single zone.
- ``localsky.stop_all``        Stop every running zone.
- ``localsky.pause``           Pause the engine for N hours.
- ``localsky.resume``          Clear an active pause.
- ``localsky.set_override``     Set the sticky global override (auto/skip/run).
- ``localsky.set_zone_override`` Set a sticky per-zone override (auto/skip/run).

Each service accepts an optional ``entry_id`` to target a specific
LocalSky deployment; without it, the action fans out to every
configured entry. The actual POST goes through
``LocalSkyCoordinator.dispatch_action`` so the coordinator refreshes
immediately after.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ACTION_CLEAR_PAUSE_UNTIL,
    ACTION_RUN,
    ACTION_SET_GLOBAL_OVERRIDE,
    ACTION_SET_PAUSE_UNTIL,
    ACTION_SET_ZONE_OVERRIDE,
    ACTION_STOP,
    ACTION_STOP_ALL,
    DOMAIN,
    STICKY_OVERRIDE_MODES,
)

_LOGGER = logging.getLogger(__name__)

ATTR_ENTRY_ID = "entry_id"
ATTR_ZONE = "zone"
ATTR_SECONDS = "seconds"
ATTR_HOURS = "hours"
ATTR_MODE = "mode"

SVC_RUN_ZONE = "run_zone"
SVC_STOP_ZONE = "stop_zone"
SVC_STOP_ALL = "stop_all"
SVC_PAUSE = "pause"
SVC_RESUME = "resume"
SVC_SET_OVERRIDE = "set_override"
SVC_SET_ZONE_OVERRIDE = "set_zone_override"

# Zone slugs the core accepts: lowercase alnum + underscore (mirrors the
# allow-list in the core's SetZoneOverride dispatch). Validated here so a bad
# slug fails in HA with a clear error instead of a 400 round-trip.
_ZONE_SLUG = vol.Match(
    r"^[a-z0-9_]+$",
    msg="zone must be a lowercase slug (letters, digits, underscores)",
)

RUN_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): cv.string,
        vol.Required(ATTR_SECONDS): vol.All(vol.Coerce(int), vol.Range(min=1, max=7200)),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

STOP_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): cv.string,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

STOP_ALL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

PAUSE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_HOURS, default=24): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24 * 30)
        ),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

RESUME_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SET_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MODE): vol.In(STICKY_OVERRIDE_MODES),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SET_ZONE_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): _ZONE_SLUG,
        vol.Required(ATTR_MODE): vol.In(STICKY_OVERRIDE_MODES),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


def _targets(hass: HomeAssistant, call: ServiceCall):
    """Yield coordinators the call should act against."""
    loaded = {
        e.entry_id: e.runtime_data
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
    }
    if not loaded:
        raise HomeAssistantError(
            "LocalSky is not configured. Add the integration before calling services."
        )
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id is not None:
        coordinator = loaded.get(entry_id)
        if coordinator is None:
            raise HomeAssistantError(
                f"No LocalSky entry with entry_id={entry_id!r}."
            )
        return [coordinator]
    return list(loaded.values())


async def _dispatch(hass: HomeAssistant, call: ServiceCall, payload: dict[str, Any]) -> None:
    for coordinator in _targets(hass, call):
        try:
            await coordinator.dispatch_action(payload)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "LocalSky service %s failed against %s: %s",
                call.service, coordinator._base_url, err,  # noqa: SLF001
            )
            raise HomeAssistantError(
                f"LocalSky {call.service} failed: {err}"
            ) from err


def async_register_services(hass: HomeAssistant) -> None:
    """Register all integration-level services. Idempotent."""

    async def _run_zone(call: ServiceCall) -> None:
        await _dispatch(
            hass,
            call,
            {"kind": ACTION_RUN, "zone": call.data[ATTR_ZONE], "seconds": call.data[ATTR_SECONDS]},
        )

    async def _stop_zone(call: ServiceCall) -> None:
        await _dispatch(
            hass, call, {"kind": ACTION_STOP, "zone": call.data[ATTR_ZONE]}
        )

    async def _stop_all(call: ServiceCall) -> None:
        await _dispatch(hass, call, {"kind": ACTION_STOP_ALL})

    async def _pause(call: ServiceCall) -> None:
        hours: int = call.data.get(ATTR_HOURS, 24)
        epoch = int(time.time()) + hours * 3600
        await _dispatch(hass, call, {"kind": ACTION_SET_PAUSE_UNTIL, "epoch": epoch})

    async def _resume(call: ServiceCall) -> None:
        await _dispatch(hass, call, {"kind": ACTION_CLEAR_PAUSE_UNTIL})

    async def _set_override(call: ServiceCall) -> None:
        await _dispatch(
            hass,
            call,
            {"kind": ACTION_SET_GLOBAL_OVERRIDE, "mode": call.data[ATTR_MODE]},
        )

    async def _set_zone_override(call: ServiceCall) -> None:
        await _dispatch(
            hass,
            call,
            {
                "kind": ACTION_SET_ZONE_OVERRIDE,
                "zone": call.data[ATTR_ZONE],
                "mode": call.data[ATTR_MODE],
            },
        )

    hass.services.async_register(DOMAIN, SVC_RUN_ZONE, _run_zone, schema=RUN_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_STOP_ZONE, _stop_zone, schema=STOP_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_STOP_ALL, _stop_all, schema=STOP_ALL_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_PAUSE, _pause, schema=PAUSE_SCHEMA)
    hass.services.async_register(DOMAIN, SVC_RESUME, _resume, schema=RESUME_SCHEMA)
    hass.services.async_register(
        DOMAIN, SVC_SET_OVERRIDE, _set_override, schema=SET_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SVC_SET_ZONE_OVERRIDE, _set_zone_override, schema=SET_ZONE_OVERRIDE_SCHEMA
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Drop all integration-level services. Called on last entry unload."""
    for svc in (
        SVC_RUN_ZONE,
        SVC_STOP_ZONE,
        SVC_STOP_ALL,
        SVC_PAUSE,
        SVC_RESUME,
        SVC_SET_OVERRIDE,
        SVC_SET_ZONE_OVERRIDE,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
