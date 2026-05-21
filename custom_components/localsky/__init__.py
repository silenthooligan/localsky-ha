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
from .services import async_register_services, async_unregister_services
from .util import format_base_url

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
    use_https: bool = entry.data.get(CONF_USE_HTTPS, False)
    base_url = format_base_url(host, port, use_https)

    session = async_get_clientsession(hass)
    coordinator = LocalSkyCoordinator(hass, session, base_url)

    # Service probe + first refresh. Either failure should keep HA from
    # registering platforms so the user sees a clear setup-failed state.
    try:
        await coordinator.fetch_info()
    except Exception as err:  # noqa: BLE001 - aiohttp + timeouts + json parse
        raise ConfigEntryNotReady(f"Cannot reach LocalSky at {base_url}: {err}") from err

    await coordinator.async_config_entry_first_refresh()

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = coordinator

    # Register integration-level services once, on the first entry setup.
    # Services act against whichever entry the caller targets (or all,
    # for stop_all).
    if len(domain_data) == 1:
        async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        # If nothing's left, unregister the services so HA's service UI
        # doesn't list orphan actions.
        if not domain_data:
            async_unregister_services(hass)
    return unload_ok
