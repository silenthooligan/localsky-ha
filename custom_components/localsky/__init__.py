"""LocalSky HA integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, CONF_PORT, CONF_USE_HTTPS, DEFAULT_PORT, DOMAIN
from .coordinator import LocalSkyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LocalSky from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scheme = "https" if entry.data.get(CONF_USE_HTTPS, False) else "http"
    base_url = f"{scheme}://{host}:{port}"

    session = async_get_clientsession(hass)
    coordinator = LocalSkyCoordinator(hass, session, base_url)

    # Service probe + first refresh. Either failure should keep HA from
    # registering platforms so the user sees a clear setup-failed state.
    try:
        await coordinator.fetch_info()
    except Exception as err:  # noqa: BLE001 - aiohttp + timeouts + json parse
        raise ConfigEntryNotReady(f"Cannot reach LocalSky at {base_url}: {err}") from err

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
