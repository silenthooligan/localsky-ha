"""DataUpdateCoordinator that polls LocalSky's REST API.

Single coordinator fetches the three snapshot endpoints in parallel
every DEFAULT_SCAN_INTERVAL and exposes the merged result via the
HA DataUpdateCoordinator pattern. Entities read from
coordinator.data[<kind>] where kind is one of tempest, irrigation,
forecast, info.

We deliberately do NOT subscribe to the SSE streams here: HA's
DataUpdateCoordinator pattern is poll-driven, and an extra background
SSE connection per HA instance is harder to lifecycle-manage than a
straightforward poll. If sub-second freshness ever matters we can add
SSE as an optional fast-path.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import API_PREFIX, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LocalSkyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll LocalSky's /api/v1/* snapshot endpoints."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        base_url: str,
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self._session = session
        # base_url is e.g. "http://192.168.1.100:8090" - no trailing slash.
        self._base_url = base_url.rstrip("/")
        # info is fetched once at setup; cached on the coordinator so
        # entity attributes can surface service_version + api_version
        # without re-polling.
        self.info: dict[str, Any] | None = None

    async def fetch_info(self) -> dict[str, Any]:
        """Hit /api/v1/info once. Surfaces service + API version."""
        url = f"{self._base_url}{API_PREFIX}/info"
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            self.info = await r.json()
            return self.info

    async def _fetch(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{API_PREFIX}{path}"
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            return await r.json()

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh all three snapshots in parallel."""
        try:
            tempest, irrigation, forecast = await asyncio.gather(
                self._fetch("/snapshot"),
                self._fetch("/irrigation/snapshot"),
                self._fetch("/forecast/snapshot"),
                return_exceptions=False,
            )
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"LocalSky API error: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed("LocalSky API timeout") from err
        return {
            "tempest": tempest,
            "irrigation": irrigation,
            "forecast": forecast,
        }

    async def dispatch_action(self, payload: dict[str, Any]) -> None:
        """POST to /api/v1/irrigation/action. Run, stop, pause, skip."""
        url = f"{self._base_url}{API_PREFIX}/irrigation/action"
        async with self._session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            r.raise_for_status()
        # Force a refresh so the running flag updates fast.
        await self.async_request_refresh()
