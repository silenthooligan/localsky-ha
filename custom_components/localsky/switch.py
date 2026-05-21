"""Per-zone run-now switch.

ON = POST /api/v1/irrigation/action with {kind: run, zone, seconds}.
OFF = POST /api/v1/irrigation/action with {kind: stop, zone}.

The switch's reported state mirrors the binary_sensor's `running` flag.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ACTION_RUN, ACTION_STOP, DOMAIN
from .coordinator import LocalSkyCoordinator

_LOGGER = logging.getLogger(__name__)

# Default seconds when the switch is turned on without a duration override.
# Matches LocalSky's "10m quick run" button on the dashboard.
DEFAULT_RUN_SECONDS = 600


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LocalSkyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    irrigation = coordinator.data.get("irrigation") if coordinator.data else None
    if irrigation:
        for zone in irrigation.get("zones", []):
            slug = zone.get("slug")
            name = zone.get("name") or slug
            if not slug:
                continue
            entities.append(LocalSkyZoneSwitch(coordinator, entry, slug, name))
    async_add_entities(entities)


class LocalSkyZoneSwitch(CoordinatorEntity[LocalSkyCoordinator], SwitchEntity):
    """on = run zone; off = stop zone."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LocalSkyCoordinator,
        entry: ConfigEntry,
        slug: str,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._slug = slug
        self._attr_unique_id = f"{entry.entry_id}_{slug}_run"
        self._attr_name = f"{zone_name} - Run"
        info = coordinator.info or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="LocalSky",
            manufacturer="silenthooligan",
            model="LocalSky",
            sw_version=info.get("service_version", "unknown"),
            configuration_url=f"http://{entry.data.get('host')}:{entry.data.get('port', 8090)}",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        for z in (data.get("irrigation") or {}).get("zones", []):
            if z.get("slug") == self._slug:
                return bool(z.get("running"))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        seconds = int(kwargs.get("duration_s", DEFAULT_RUN_SECONDS))
        await self.coordinator.dispatch_action(
            {"kind": ACTION_RUN, "zone": self._slug, "seconds": seconds}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.dispatch_action(
            {"kind": ACTION_STOP, "zone": self._slug}
        )
