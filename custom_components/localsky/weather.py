"""Single weather entity built from LocalSky's Tempest snapshot.

Drops the need for a separate WeatherFlow integration in HA when
LocalSky is the source-of-truth (LocalSky already ingests Tempest UDP
broadcasts directly). Daily and hourly forecasts are pulled from the
forecast snapshot when present.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.sun import is_up
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# How many hours of the snapshot's hourly block to publish. LocalSky keeps
# well over a hundred entries (NWS returns ~156); HA's forecast consumers and
# the recorder only ever want the near term, so cap at two days.
_HOURLY_LIMIT = 48

from .const import DOMAIN
from .coordinator import LocalSkyCoordinator
from .util import device_info_for

_LOGGER = logging.getLogger(__name__)


# Older servers lack the shared sky decision (introduced in API 2.5).
# Keep their legacy mapping for compatibility. New servers own the decision.
#
# `forecast` is the forecast snapshot; on a cloud-only install (no live local
# station: snap.has_live_station is false) the solar-only heuristic has no real
# signal at night and would always read "clear-night", so we fall back to the
# nearest-hour forecast weather_code instead.
def _condition_from_snapshot(
    tempest: dict[str, Any],
    forecast: dict[str, Any] | None = None,
) -> str | None:
    # API 2.5 owns the sky decision. Explicit unknown/malformed new data must
    # remain unknown, not fall through to the legacy brightness heuristic.
    if "sky" in tempest:
        return _condition_from_sky(tempest["sky"])
    precip_type = tempest.get("precip_type")
    rain_in_hr = float(tempest.get("rain_intensity_in_hr") or 0)
    lightning = int(tempest.get("lightning_strikes_last_hour") or 0)
    if precip_type == 2:
        return "hail"
    if lightning > 0:
        return "lightning-rainy" if rain_in_hr > 0 else "lightning"
    if precip_type == 1 or rain_in_hr > 0:
        if rain_in_hr >= 0.3:
            return "pouring"
        return "rainy"

    # Cloud-only install (no live local weather station): the solar-only
    # heuristic below is meaningless (solar reads 0 every night and the
    # forecast-filled current carries no live cloud-cover signal), so a cloudy
    # or overcast night would wrongly paint "clear-night". Prefer the
    # nearest-hour forecast weather_code, which is a real sky-condition signal.
    if not tempest.get("has_live_station", False):
        wmo = _condition_from_nearest_hour(forecast)
        if wmo is not None:
            return wmo

    solar = float(tempest.get("solar_w_m2") or 0)
    wind = float(tempest.get("wind_avg_mph") or 0)
    if wind >= 18:
        return "windy"
    if solar > 600:
        return "sunny"
    if solar > 200:
        return "partlycloudy"
    if solar > 30:
        return "cloudy"
    return "clear-night"


def _condition_from_sky(sky: Any) -> str | None:
    """Map LocalSky's evidence-based condition to HA's smaller vocabulary."""
    if not isinstance(sky, dict):
        return None
    condition = sky.get("condition")
    if condition == "clear":
        if sky.get("is_day") is True:
            return "sunny"
        if sky.get("is_day") is False:
            return "clear-night"
        return None
    if condition == "thunderstorm":
        return "lightning-rainy" if sky.get("precipitating") is True else "lightning"
    # HA has no generic low-visibility condition. Calling smoke/dust "fog"
    # would claim a cause that the server deliberately leaves unknown.
    return {
        "mostly_clear": "partlycloudy", "partly_cloudy": "partlycloudy",
        "mostly_cloudy": "cloudy", "overcast": "cloudy", "fog": "fog",
        "light_rain": "rainy", "rain": "rainy", "heavy_rain": "pouring",
        "snow": "snowy", "wintry_mix": "snowy-rainy", "hail": "hail",
    }.get(condition) if isinstance(condition, str) else None


def _condition_from_nearest_hour(forecast: dict[str, Any] | None) -> str | None:
    """Map the forecast's nearest-hour WMO weather_code to an HA condition.

    Used as the current condition on a cloud-only install where there is no
    live cloud/precip signal. Picks the hourly entry whose `time_epoch` is
    closest to now. Returns None when the forecast carries no usable hourly
    data (caller then falls through to the solar heuristic).
    """
    if not isinstance(forecast, dict):
        return None
    hourly = forecast.get("hourly") or []
    if not isinstance(hourly, list) or not hourly:
        return None
    now = datetime.now(tz=timezone.utc).timestamp()
    nearest: dict[str, Any] | None = None
    best_delta: float | None = None
    for h in hourly:
        if not isinstance(h, dict):
            continue
        ts = h.get("time_epoch")
        if not isinstance(ts, (int, float)):
            continue
        delta = abs(float(ts) - now)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            nearest = h
    if nearest is None:
        return None
    return _condition_from_wmo(nearest.get("weather_code"))


# LocalSky's forecast snapshot carries Open-Meteo WMO weather codes per day.
# Map them to HA's daily-forecast condition vocabulary. Daily forecast is a
# daytime summary, so code 0 is "sunny" (never "clear-night").
_WMO_TO_CONDITION = {
    0: "sunny",
    1: "partlycloudy", 2: "partlycloudy",
    3: "cloudy",
    45: "fog", 48: "fog",
    51: "rainy", 53: "rainy", 55: "rainy",
    56: "snowy-rainy", 57: "snowy-rainy",
    61: "rainy", 63: "rainy", 65: "pouring",
    66: "snowy-rainy", 67: "snowy-rainy",
    71: "snowy", 73: "snowy", 75: "snowy", 77: "snowy",
    80: "rainy", 81: "rainy", 82: "pouring",
    85: "snowy", 86: "snowy",
    95: "lightning",
    96: "lightning-rainy", 99: "lightning-rainy",
}


def _condition_from_wmo(code: Any) -> str | None:
    if isinstance(code, bool):
        return None
    try:
        return _WMO_TO_CONDITION.get(int(code))
    except (TypeError, ValueError, OverflowError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LocalSkyCoordinator = entry.runtime_data
    async_add_entities([LocalSkyWeather(coordinator, entry)])


class LocalSkyWeather(CoordinatorEntity[LocalSkyCoordinator], WeatherEntity):
    """Backed by LocalSky's live Tempest + forecast snapshots."""

    _attr_has_entity_name = True
    _attr_name = "Weather"
    _attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_native_pressure_unit = UnitOfPressure.INHG
    _attr_native_wind_speed_unit = UnitOfSpeed.MILES_PER_HOUR
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.INCHES
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: LocalSkyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = device_info_for(entry, coordinator, "tempest")

    def _tempest(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("tempest") or {}

    def _forecast(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("forecast") or {}

    @property
    def condition(self) -> str | None:
        return _condition_from_snapshot(self._tempest(), self._forecast())

    @property
    def native_temperature(self) -> float | None:
        v = self._tempest().get("air_temp_f")
        return _as_float(v)

    @property
    def native_apparent_temperature(self) -> float | None:
        v = self._tempest().get("feels_like_f")
        return _as_float(v)

    @property
    def native_dew_point(self) -> float | None:
        v = self._tempest().get("dew_point_f")
        return _as_float(v)

    @property
    def humidity(self) -> float | None:
        v = self._tempest().get("rh_pct")
        return _as_float(v)

    @property
    def native_pressure(self) -> float | None:
        v = self._tempest().get("pressure_inhg")
        return _as_float(v)

    @property
    def native_wind_speed(self) -> float | None:
        v = self._tempest().get("wind_avg_mph")
        return _as_float(v)

    @property
    def native_wind_gust_speed(self) -> float | None:
        v = self._tempest().get("wind_gust_mph")
        return _as_float(v)

    @property
    def wind_bearing(self) -> float | None:
        v = self._tempest().get("wind_dir_deg")
        return _as_float(v)

    @property
    def uv_index(self) -> float | None:
        v = self._tempest().get("uv_index")
        return _as_float(v)

    async def async_forecast_daily(self) -> list[Forecast] | None:
        forecast = (self.coordinator.data or {}).get("forecast") or {}
        days = forecast.get("daily") or forecast.get("days") or []
        if not isinstance(days, list):
            return None
        out: list[Forecast] = []
        for d in days:
            if len(out) >= 7:
                break
            if not isinstance(d, dict):
                continue
            # LocalSky's forecast snapshot uses `time_epoch`; keep the older
            # keys as fallbacks for forward/backward compatibility.
            ts = d.get("time_epoch") or d.get("epoch") or d.get("date_epoch")
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                continue
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
            condition = _condition_from_wmo(d.get("weather_code"))
            if condition is None:
                condition = d.get("condition")
            out.append(
                Forecast(
                    datetime=dt.isoformat(),
                    native_temperature=_as_float(d.get("temp_max_f")),
                    native_templow=_as_float(d.get("temp_min_f")),
                    native_precipitation=_as_float(
                        d.get("precip_sum_in") if d.get("precip_sum_in") is not None else d.get("precip_in")
                    ),
                    precipitation_probability=_as_int(
                        d.get("precip_probability_max")
                        if d.get("precip_probability_max") is not None
                        else d.get("precip_prob_pct")
                    ),
                    native_wind_speed=_as_float(d.get("wind_max_mph")),
                    condition=condition,
                )
            )
        return out or None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Publish the snapshot's hourly block.

        The data was already being fetched and cached for
        `_condition_from_nearest_hour`; this exposes it so consumers can ask
        what the weather will be at a given hour instead of only what it is
        now. That matters most for providers with real convective forecasting:
        NWS marks thunderstorm hours (WMO 95 via its shortForecast text) and
        carries a per-hour probability of precipitation, neither of which is
        reachable through a daily summary.
        """
        forecast = self._forecast()
        hours = forecast.get("hourly") or []
        if not isinstance(hours, list):
            return None
        out: list[Forecast] = []
        # Cap on USABLE entries rather than slicing the raw list first: a
        # malformed entry near the front would otherwise consume one of the
        # published hours and silently shorten the forecast.
        for h in hours:
            if len(out) >= _HOURLY_LIMIT:
                break
            if not isinstance(h, dict):
                continue
            ts = h.get("time_epoch")
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                continue
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
            out.append(
                Forecast(
                    datetime=dt.isoformat(),
                    condition=self._hourly_condition(h.get("weather_code"), dt),
                    native_temperature=_as_float(h.get("temp_f")),
                    native_apparent_temperature=_as_float(h.get("apparent_temp_f")),
                    native_precipitation=_as_float(h.get("precip_in")),
                    precipitation_probability=_as_int(h.get("precip_probability")),
                    native_wind_speed=_as_float(h.get("wind_mph")),
                    wind_bearing=_as_float(h.get("wind_dir_deg")),
                    humidity=_as_int(h.get("humidity_pct")),
                    cloud_coverage=_as_int(h.get("cloud_cover_pct")),
                )
            )
        return out or None

    def _hourly_condition(self, code: Any, dt: datetime) -> str | None:
        """WMO code to HA condition, night-aware.

        `_WMO_TO_CONDITION` maps clear sky to "sunny" because it was written
        for the daily forecast, which is a daytime summary. An hourly forecast
        covers actual nights, so a clear 02:00 has to read "clear-night" or the
        frontend paints a sun in the dark. Only the clear-sky code is
        ambiguous; every other condition looks the same at any hour.
        """
        condition = _condition_from_wmo(code)
        if condition != "sunny":
            return condition
        try:
            if not is_up(self.hass, dt):
                return "clear-night"
        except Exception:  # noqa: BLE001 - sun helper needs configured lat/lon
            _LOGGER.debug("sun position unavailable for %s", dt)
            return None
        return condition


def _as_float(v: Any) -> float | None:
    try:
        value = float(v) if v is not None and not isinstance(v, bool) else None
        return value if value is not None and math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _as_int(v: Any) -> int | None:
    try:
        value = _as_float(v)
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None
