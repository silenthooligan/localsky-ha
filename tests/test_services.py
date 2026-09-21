"""Forecast services preserve server evidence and select one installation."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.localsky.services import (
    async_register_services,
    async_unregister_services,
)
from .test_coordinator import _coordinator, _FakeResponse, _FakeSession


DATA = {
    "start": "2026-09-21T13:00:00-04:00",
    "end": "2026-09-21T14:00:00-04:00",
}
WINDOW = {
    "track": "merged", "fetched_at": 1000, "age_s": 9000,
    "hours": 0, "complete": False, "precip_sum_in": None, "hourly": [],
}


@pytest.mark.asyncio
async def test_forecast_window_returns_original_age_and_nulls(hass):
    session = _FakeSession(_FakeResponse(body=WINDOW))
    coordinator = _coordinator(hass, session=session)
    coordinator.info = {"api_version": "2.3.0"}
    entry = SimpleNamespace(entry_id="one", runtime_data=coordinator)
    async_register_services(hass)
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=[entry]):
        result = await hass.services.async_call(
            "localsky", "get_forecast_window", DATA, blocking=True, return_response=True
        )
    assert result == WINDOW
    method, url, _kwargs = session.calls[0]
    assert method == "GET"
    assert parse_qs(urlsplit(url).query) == {
        "track": ["merged"],
        "from": [str(int(datetime.fromisoformat(DATA["start"]).timestamp()))],
        "to": [str(int(datetime.fromisoformat(DATA["end"]).timestamp()))],
    }
    async_unregister_services(hass)
    assert not hass.services.has_service("localsky", "get_forecast_window")


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["2.2.0", "1.13.0", None, "invalid"])
async def test_forecast_window_requires_the_additive_api(hass, version):
    session = _FakeSession(_FakeResponse(body={"api_version": version}))
    coordinator = _coordinator(hass, session=session)
    coordinator.info = {"api_version": version}
    with pytest.raises(UpdateFailed, match="API 2.3.0"):
        await coordinator.get_forecast_window("merged", 1000, 2000)
    assert len(session.calls) == 1
    assert urlsplit(session.calls[0][1]).path.endswith("/info")


@pytest.mark.asyncio
async def test_forecast_window_notices_server_upgrade_without_reloading_ha(hass):
    session = MagicMock()
    session.get.side_effect = [
        _FakeResponse(body={"api_version": "2.3.0"}),
        _FakeResponse(body=WINDOW),
    ]
    coordinator = _coordinator(hass, session=session)
    coordinator.info = {"api_version": "2.2.0"}
    result = await coordinator.get_forecast_window("nbm", 1000, 2000)
    assert result == WINDOW
    assert coordinator.info["api_version"] == "2.3.0"
    assert urlsplit(session.get.call_args_list[0].args[0]).path.endswith("/info")
    assert urlsplit(session.get.call_args_list[1].args[0]).path.endswith("/forecast/window")


@pytest.mark.asyncio
async def test_forecast_window_requires_a_single_target(hass):
    coordinators = [SimpleNamespace(get_forecast_window=AsyncMock(return_value=WINDOW)) for _ in range(2)]
    entries = [SimpleNamespace(entry_id=str(n), runtime_data=c) for n, c in enumerate(coordinators)]
    async_register_services(hass)
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=entries):
        with pytest.raises(HomeAssistantError, match="entry_id"):
            await hass.services.async_call("localsky", "get_forecast_window", DATA, blocking=True, return_response=True)
        result = await hass.services.async_call("localsky", "get_forecast_window", {**DATA, "entry_id": "1", "track": "nbm"}, blocking=True, return_response=True)
    assert result == WINDOW
    coordinators[0].get_forecast_window.assert_not_awaited()
    assert coordinators[1].get_forecast_window.await_args.args[0] == "nbm"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure, message", [
    (aiohttp.ClientResponseError(MagicMock(), (), status=404), "Unknown LocalSky forecast track"),
    (aiohttp.ClientConnectionError(), "Could not reach LocalSky"),
])
async def test_forecast_window_reports_unknown_track_and_outage(hass, failure, message):
    coordinator = SimpleNamespace(get_forecast_window=AsyncMock(side_effect=failure))
    entry = SimpleNamespace(entry_id="one", runtime_data=coordinator)
    async_register_services(hass)
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=[entry]):
        with pytest.raises(HomeAssistantError, match=message):
            await hass.services.async_call("localsky", "get_forecast_window", DATA, blocking=True, return_response=True)


@pytest.mark.asyncio
async def test_forecast_window_rejects_reversed_range_without_network(hass):
    coordinator = SimpleNamespace(get_forecast_window=AsyncMock())
    entry = SimpleNamespace(entry_id="one", runtime_data=coordinator)
    async_register_services(hass)
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=[entry]):
        with pytest.raises(HomeAssistantError, match="ordered forecast window"):
            await hass.services.async_call("localsky", "get_forecast_window", {"start": DATA["end"], "end": DATA["start"]}, blocking=True, return_response=True)
    coordinator.get_forecast_window.assert_not_awaited()
