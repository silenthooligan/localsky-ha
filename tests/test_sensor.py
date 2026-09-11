"""Manifest-driven entities: creation, value walking, zone paths."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import entity_registry as er

from custom_components.localsky.const import DOMAIN
from custom_components.localsky.coordinator import LocalSkyCoordinator

from .conftest import INFO_OPEN

ENTRY_DATA = {"host": "192.0.2.10", "port": 8090, "use_https": False}

MANIFEST = {
    "entities": [
        {
            "id": "air_temp_f",
            "platform": "sensor",
            "name": "Air temperature",
            "snapshot": "tempest",
            "path": ["air_temp_f"],
            "unit": "°F",
            "device_class": "temperature",
        },
        {
            "id": "rain_in_today",
            "platform": "sensor",
            "name": "Rain today",
            "snapshot": "tempest",
            "path": ["rain_in_today"],
            "unit": "in",
        },
        {
            "id": "front_soil_moisture",
            "platform": "sensor",
            "name": "Front - Soil moisture",
            "snapshot": "irrigation",
            "path": ["soil_pct"],
            "zone_slug": "front",
            "unit": "%",
        },
        # Non-sensor platforms must be ignored by sensor setup.
        {
            "id": "front_running",
            "platform": "binary_sensor",
            "name": "Front running",
            "snapshot": "irrigation",
            "path": ["running"],
            "zone_slug": "front",
        },
    ]
}

DATA = {
    "tempest": {"air_temp_f": 84.2, "rain_in_today": 0.37},
    "irrigation": {
        "zones": [{"slug": "front", "name": "Front", "soil_pct": 41.5}],
        "skip_check": {"verdict": "run"},
    },
    "forecast": {"daily": []},
}


async def _setup(
    hass: HomeAssistant, *, manifest=MANIFEST, data=DATA
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id=INFO_OPEN["uuid"]
    )
    entry.add_to_hass(hass)

    async def _start(self: LocalSkyCoordinator) -> None:
        self.async_set_updated_data(data)

    with patch.object(
        LocalSkyCoordinator, "fetch_info", new=AsyncMock(return_value=INFO_OPEN)
    ), patch.object(
        LocalSkyCoordinator, "fetch_manifest", new=AsyncMock(return_value=manifest)
    ), patch.object(
        LocalSkyCoordinator, "async_start", new=_start
    ), patch.object(
        LocalSkyCoordinator, "async_stop", new=AsyncMock()
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entry, key: str):
    """Resolve a manifest entity by unique_id; entity_id naming is the
    registry's business, not the test's."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    return hass.states.get(entity_id) if entity_id else None


@pytest.mark.asyncio
async def test_manifest_sensors_created_with_values(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    temp = _state(hass, entry, "air_temp_f")
    assert temp is not None
    assert float(temp.state) == 84.2
    assert temp.attributes["unit_of_measurement"] == "°F"

    rain = _state(hass, entry, "rain_in_today")
    assert rain is not None
    assert float(rain.state) == 0.37


@pytest.mark.asyncio
async def test_zone_scoped_path_resolves_through_zones_list(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    soil = _state(hass, entry, "front_soil_moisture")
    assert soil is not None
    assert float(soil.state) == 41.5


@pytest.mark.asyncio
async def test_sensor_setup_ignores_other_platform_descriptors(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    # The binary_sensor descriptor must not materialize as a sensor.
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_front_running")
        is None
    )


@pytest.mark.asyncio
async def test_values_update_with_coordinator_data(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    coordinator: LocalSkyCoordinator = entry.runtime_data
    updated = {**DATA, "tempest": {**DATA["tempest"], "air_temp_f": 70.1}}
    coordinator.async_set_updated_data(updated)
    await hass.async_block_till_done()
    assert float(_state(hass, entry, "air_temp_f").state) == 70.1


@pytest.mark.asyncio
async def test_api2_forecast_summary_nulls_become_unknown_and_zero_remains_real(
    hass: HomeAssistant,
) -> None:
    fields = (
        "wind_max_today_mph",
        "temp_min_24h_f",
        "temp_max_3day_f",
        "humidity_now_pct",
        "heat_index_now_f",
        "heat_index_max_3day_f",
    )
    manifest = {
        "entities": [
            {
                "id": field,
                "platform": "sensor",
                "name": field,
                "snapshot": "irrigation",
                "path": ["forecast", field],
                "group": "forecast",
            }
            for field in fields
        ]
    }
    data = {
        **DATA,
        "irrigation": {
            **DATA["irrigation"],
            "forecast": dict.fromkeys(fields, None),
        },
    }
    entry = await _setup(hass, manifest=manifest, data=data)
    for field in fields:
        state = _state(hass, entry, field)
        assert state is not None
        assert state.state == "unknown"

    entry.runtime_data.async_set_updated_data(
        {
            **data,
            "irrigation": {
                **data["irrigation"],
                "forecast": dict.fromkeys(fields, 0.0),
            },
        }
    )
    await hass.async_block_till_done()
    for field in fields:
        assert float(_state(hass, entry, field).state) == 0.0
