"""Source-label prettifying and weather sub-device name upkeep."""
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localsky.const import DOMAIN
from custom_components.localsky.util import (
    async_sync_weather_device_name,
    device_info_for,
    prettify_source_label,
)


def _coordinator(source_label):
    """Minimal stand-in: only `data` is read for the device label."""
    data = {"tempest": {}} if source_label is None else {"tempest": {"source_label": source_label}}
    return SimpleNamespace(data=data, info=None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Config ids LocalSky reports verbatim for non-station sources.
        ("open_meteo", "Open-Meteo"),
        ("noaa_mrms", "NOAA MRMS"),
        ("nws", "NWS"),
        ("ecowitt_gw_poll", "Ecowitt"),
        # Already a display name: untouched.
        ("Tempest", "Tempest"),
        ("Ecowitt", "Ecowitt"),
        # A user's own id still reads as words rather than a slug.
        ("back_yard_station", "Back Yard Station"),
        ("roof-station", "Roof Station"),
        ("", ""),
    ],
)
def test_prettify_source_label(raw, expected):
    assert prettify_source_label(raw) == expected


def test_weather_device_name_uses_the_display_label():
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10", "port": 8090})
    info = device_info_for(entry, _coordinator("open_meteo"), group="tempest")
    assert info["name"] == "LocalSky Open-Meteo"
    assert info["model"] == "Open-Meteo weather source"


async def test_sync_renames_the_device_when_the_owner_changes(hass: HomeAssistant) -> None:
    """The restart race: a device registered while the cloud fill owned
    conditions must not keep that name once the station owns them again."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10", "port": 8090})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_tempest")},
        name="LocalSky Open-Meteo",
        model="Open-Meteo weather source",
    )

    async_sync_weather_device_name(hass, entry, _coordinator("Tempest"))
    device = registry.async_get(device.id)
    assert device.name == "LocalSky Tempest"
    assert device.model == "Tempest weather source"


async def test_sync_never_overrides_a_user_named_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10", "port": 8090})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_tempest")},
        name="LocalSky Open-Meteo",
    )
    registry.async_update_device(device.id, name_by_user="Backyard weather")

    async_sync_weather_device_name(hass, entry, _coordinator("Tempest"))
    device = registry.async_get(device.id)
    assert device.name_by_user == "Backyard weather"


async def test_sync_leaves_the_name_alone_before_the_first_reading(hass: HomeAssistant) -> None:
    """A transient gap with no source label must not churn the device back to
    the neutral placeholder."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10", "port": 8090})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_tempest")},
        name="LocalSky Tempest",
    )

    async_sync_weather_device_name(hass, entry, _coordinator(None))
    assert registry.async_get(device.id).name == "LocalSky Tempest"
