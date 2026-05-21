"""Per-zone running binary sensor."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LocalSkyCoordinator
from .util import format_base_url


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LocalSkyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []
    irrigation = coordinator.data.get("irrigation") if coordinator.data else None
    if irrigation:
        for zone in irrigation.get("zones", []):
            slug = zone.get("slug")
            name = zone.get("name") or slug
            if not slug:
                continue
            entities.append(LocalSkyZoneRunningBinary(coordinator, entry, slug, name))
    # System-wide running (any zone): also useful for automations.
    entities.append(LocalSkyAnyZoneRunning(coordinator, entry))
    async_add_entities(entities)


class _LocalSkyBaseBinary(CoordinatorEntity[LocalSkyCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LocalSkyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        info = coordinator.info or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="LocalSky",
            manufacturer="LocalSky",
            model="LocalSky Service",
            sw_version=info.get("service_version", "unknown"),
            configuration_url=format_base_url(
                entry.data.get("host", ""),
                entry.data.get("port", 8090),
                entry.data.get("use_https", False),
            ),
        )


class LocalSkyZoneRunningBinary(_LocalSkyBaseBinary):
    """on = this zone is actively running."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: LocalSkyCoordinator,
        entry: ConfigEntry,
        slug: str,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._slug = slug
        self._attr_unique_id = f"{entry.entry_id}_{slug}_running"
        self._attr_name = f"{zone_name} - Running"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        for z in (data.get("irrigation") or {}).get("zones", []):
            if z.get("slug") == self._slug:
                return bool(z.get("running"))
        return None


class LocalSkyAnyZoneRunning(_LocalSkyBaseBinary):
    """on = any LocalSky zone is currently running."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: LocalSkyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_any_running"
        self._attr_name = "Any zone running"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        zones = (data.get("irrigation") or {}).get("zones", [])
        if not zones:
            return None
        return any(z.get("running") for z in zones)
