"""Entry lifecycle: setup, runtime_data, services, unload, not-ready."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localsky.const import DOMAIN
from custom_components.localsky.coordinator import LocalSkyCoordinator
from custom_components.localsky.util import device_info_for

from .conftest import INFO_OPEN

ENTRY_DATA = {"host": "192.0.2.10", "port": 8090, "use_https": False}

SERVICES = ("run_zone", "stop_zone", "stop_all")


async def test_registry_identity_and_parent_links_survive_reload(hass: HomeAssistant, caplog) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, name="LocalSky"
    )
    area = ar.async_get(hass).async_create("Garden")
    registry.async_update_device(hub.id, name_by_user="My LocalSky", area_id=area.id)
    existing = {}
    for group in ("tempest", "irrigation", "forecast"):
        child = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_{group}")}, name=group,
        )
        registry.async_update_device(child.id, via_device_id=hub.id, name_by_user=f"My {group}", area_id=area.id)
        existing[group] = child.id
    p1, p2, p3, p4 = _patched_network()
    with p1, p2, p3, p4:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = er.async_get(hass)
        before = {e.entity_id: (e.unique_id, e.device_id) for e in
                  er.async_entries_for_config_entry(entities, entry.entry_id)}
        assert before
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert {e.entity_id: (e.unique_id, e.device_id) for e in
                er.async_entries_for_config_entry(entities, entry.entry_id)} == before
        assert entry.runtime_data.hub_device_id == hub.id
        assert registry.async_get(hub.id).name_by_user == "My LocalSky"
        for group, device_id in existing.items():
            info = device_info_for(entry, entry.runtime_data, group)
            if "via_device_id" in dr.DeviceInfo.__annotations__:
                assert info["via_device_id"] == hub.id
                assert "via_device" not in info
            else:
                assert info["via_device"] == (DOMAIN, entry.entry_id)
            device = registry.async_get_or_create(config_entry_id=entry.entry_id, **info)
            assert device.id == device_id
            assert device.via_device_id == hub.id
            assert device.name_by_user == f"My {group}"
            assert device.area_id == area.id
        assert not [r for r in caplog.records if "localsky" in r.message.lower()
                    and "deprecated" in r.message.lower() and "device" in r.message.lower()]


def _entry(uid: str = INFO_OPEN["uuid"]) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=uid)


def _patched_network(api_version: str = INFO_OPEN["api_version"]):
    """Silence network I/O while retaining fetch_info's metadata side effect."""
    async def fetch_info(coordinator):
        coordinator.info = {**INFO_OPEN, "api_version": api_version}
        return coordinator.info

    return (
        patch.object(LocalSkyCoordinator, "fetch_info", new=fetch_info),
        patch.object(LocalSkyCoordinator, "fetch_manifest", new=AsyncMock(return_value=None)),
        patch.object(LocalSkyCoordinator, "async_start", new=AsyncMock()),
        patch.object(LocalSkyCoordinator, "async_stop", new=AsyncMock()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("api_version", ["1.13.0", "2.0.0"])
async def test_setup_populates_runtime_data_and_services(
    hass: HomeAssistant, api_version: str
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    p1, p2, p3, p4 = _patched_network(api_version)
    with p1, p2, p3, p4:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert isinstance(entry.runtime_data, LocalSkyCoordinator)
        assert entry.runtime_data.info["api_version"] == api_version
        for svc in SERVICES:
            assert hass.services.has_service(DOMAIN, svc)


@pytest.mark.asyncio
async def test_unload_stops_coordinator_and_drops_services(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    p1, p2, p3, p4 = _patched_network()
    with p1, p2, p3, p4:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.NOT_LOADED
        coordinator.async_stop.assert_awaited()
        for svc in SERVICES:
            assert not hass.services.has_service(DOMAIN, svc)


@pytest.mark.asyncio
async def test_services_survive_until_last_entry_unloads(hass: HomeAssistant) -> None:
    first = _entry()
    second = _entry(uid="99999999-2222-4333-8444-555555555555")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    p1, p2, p3, p4 = _patched_network()
    with p1, p2, p3, p4:
        # Setting up the first entry loads the component, which sets up
        # every registered entry of the domain, including the second.
        assert await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()
        assert second.state is ConfigEntryState.LOADED

        assert await hass.config_entries.async_unload(first.entry_id)
        await hass.async_block_till_done()
        # One LocalSky still loaded: services must remain callable.
        for svc in SERVICES:
            assert hass.services.has_service(DOMAIN, svc)

        assert await hass.config_entries.async_unload(second.entry_id)
        await hass.async_block_till_done()
        for svc in SERVICES:
            assert not hass.services.has_service(DOMAIN, svc)


@pytest.mark.asyncio
async def test_unreachable_server_defers_setup(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    with patch.object(
        LocalSkyCoordinator,
        "fetch_info",
        new=AsyncMock(side_effect=OSError("connection refused")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.asyncio
@pytest.mark.parametrize("api_version", ["3.0.0", "99.0.0"])
async def test_newer_api_major_refuses_setup_before_starting_coordinator(
    hass: HomeAssistant, api_version: str, caplog
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    p1, p2, p3, p4 = _patched_network(api_version)
    with p1, p2, p3 as start, p4:
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        start.assert_not_awaited()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert f"speaks API v{api_version}" in caplog.text
    assert "Update the LocalSky integration" in caplog.text
    for svc in SERVICES:
        assert not hass.services.has_service(DOMAIN, svc)
