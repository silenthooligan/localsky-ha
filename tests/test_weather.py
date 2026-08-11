"""Weather entity: hourly forecast mapping.

The hourly block is what carries a provider's convective forecasting. NWS
marks thunderstorm hours as WMO 95 (mapped from its shortForecast text) and
gives a per-hour probability of precipitation; neither survives a daily
summary, so these tests pin the field mapping that exposes them.
"""
from datetime import datetime, timezone

import pytest
from homeassistant.components.weather import WeatherEntityFeature

from custom_components.localsky import weather as mod
from custom_components.localsky.weather import _condition_from_wmo, _HOURLY_LIMIT


class FakeWeather:
    """Exercises the mapping without standing up a full HA entity.

    Borrows the real methods so the code under test is the shipped code; only
    the coordinator payload and `hass` are stubbed.
    """

    _hourly_condition = mod.LocalSkyWeather._hourly_condition
    async_forecast_hourly = mod.LocalSkyWeather.async_forecast_hourly

    def __init__(self, forecast):
        self._fc = forecast
        self.hass = object()

    def _forecast(self):
        return self._fc


def _hour(epoch, code=0, **kw):
    base = {
        "time_epoch": epoch,
        "weather_code": code,
        "temp_f": 95.0,
        "apparent_temp_f": 103.0,
        "precip_in": 0.05,
        "precip_probability": 40,
        "wind_mph": 7.0,
        "wind_dir_deg": 180,
        "humidity_pct": 70,
        "cloud_cover_pct": 60,
    }
    base.update(kw)
    return base


def test_entity_declares_both_forecast_kinds():
    """Daily must survive the addition of hourly."""
    src = mod.LocalSkyWeather.__doc__ or ""
    del src  # documentation only; the flags themselves are asserted below
    flags = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    # Read the declared value out of the class body: HA's CachedProperties
    # metaclass replaces _attr_* with descriptors, so the plain attribute
    # lookup returns a property object rather than the int.
    declared = None
    for klass in mod.LocalSkyWeather.__mro__:
        v = klass.__dict__.get("_attr_supported_features")
        if isinstance(v, int):
            declared = v
            break
    assert declared == flags


@pytest.mark.asyncio
async def test_hourly_maps_every_field(monkeypatch):
    monkeypatch.setattr(mod, "is_up", lambda hass, dt: True)

    out = await FakeWeather({"hourly": [_hour(1_760_000_000, code=95)]}).async_forecast_hourly()

    assert len(out) == 1
    f = out[0]
    # WMO 95 is what NWS emits for "Chance Showers And Thunderstorms"; it has
    # to reach HA as a lightning condition or storm automations cannot see it.
    assert f["condition"] == "lightning"
    assert f["precipitation_probability"] == 40
    assert f["native_temperature"] == 95.0
    assert f["native_apparent_temperature"] == 103.0
    assert f["native_precipitation"] == 0.05
    assert f["native_wind_speed"] == 7.0
    assert f["humidity"] == 70
    assert f["cloud_coverage"] == 60
    assert f["datetime"].startswith("20")


@pytest.mark.asyncio
async def test_hourly_clear_sky_is_night_aware(monkeypatch):
    """Code 0 means clear, which is 'sunny' by day and 'clear-night' by night.

    The shared WMO table maps 0 to 'sunny' because it was written for the
    daily forecast, which only ever describes daytime.
    """
    dt = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
    payload = {"hourly": [_hour(int(dt.timestamp()), code=0)]}

    monkeypatch.setattr(mod, "is_up", lambda hass, when: False)
    night = await FakeWeather(payload).async_forecast_hourly()
    assert night[0]["condition"] == "clear-night"

    monkeypatch.setattr(mod, "is_up", lambda hass, when: True)
    day = await FakeWeather(payload).async_forecast_hourly()
    assert day[0]["condition"] == "sunny"


@pytest.mark.asyncio
async def test_hourly_survives_sun_helper_failure(monkeypatch):
    """An unconfigured location must not take the whole forecast down."""

    def boom(hass, when):
        raise RuntimeError("no location configured")

    monkeypatch.setattr(mod, "is_up", boom)

    out = await FakeWeather({"hourly": [_hour(1_760_000_000, code=0)]}).async_forecast_hourly()

    assert out[0]["condition"] == "sunny"


@pytest.mark.asyncio
async def test_hourly_skips_junk_and_caps_length(monkeypatch):
    monkeypatch.setattr(mod, "is_up", lambda hass, when: True)
    hours = [_hour(1_760_000_000 + i * 3600) for i in range(_HOURLY_LIMIT + 20)]
    hours.insert(0, {"weather_code": 0})  # no time_epoch -> unusable
    hours.insert(1, "not-a-dict")

    out = await FakeWeather({"hourly": hours}).async_forecast_hourly()

    assert len(out) == _HOURLY_LIMIT


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"hourly": []}, {"hourly": "nope"}])
async def test_hourly_absent_returns_none(monkeypatch, payload):
    monkeypatch.setattr(mod, "is_up", lambda hass, when: True)

    assert await FakeWeather(payload).async_forecast_hourly() is None


def test_wmo_thunderstorm_codes_map_to_lightning():
    assert _condition_from_wmo(95) == "lightning"
    assert _condition_from_wmo(96) == "lightning-rainy"
    assert _condition_from_wmo(99) == "lightning-rainy"
    assert _condition_from_wmo(None) is None
    assert _condition_from_wmo("junk") is None
