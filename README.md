<p align="center"><img src="custom_components/localsky/brand/icon@2x.png" alt="" width="88" height="88"></p>
<h1 align="center">LocalSky for Home Assistant</h1>
<p align="center"><strong>Your LocalSky weather, zones, and watering controls in Home Assistant.</strong></p>
<p align="center"><a href="https://localsky.io/docs/hacs">Setup guide</a> · <a href="https://localsky.io/docs/hacs#forecast-window-action">Forecast automations</a> · <a href="https://github.com/silenthooligan/localsky-ha/issues">Get help</a></p>

Connect a running [LocalSky server](https://github.com/silenthooligan/localsky) to Home Assistant. This companion integration adds native weather and sensor entities, zone valves, and watering actions. Live updates arrive over LocalSky's event streams.

**LocalSky runs the irrigation engine. This integration connects it to Home Assistant.**

## Install and connect

1. In **HACS**, search for **LocalSky** and install it.
2. Restart Home Assistant.
3. Open **Settings → Devices & services** and add the discovered LocalSky instance. If it is not discovered, choose **Add integration → LocalSky**.
4. Enter the server address and port, normally `8090`. If authentication is enabled, use an API token from **LocalSky → Settings → Account**.

[![Open LocalSky in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=silenthooligan&repository=localsky-ha&category=integration)

[![Add the LocalSky integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=localsky)

Discovery needs network reachability. Manual pairing works when multicast discovery cannot cross your network.

## What appears in Home Assistant

| Area | Available entities and actions |
|---|---|
| Weather | Current conditions, daily forecast, and station readings |
| Irrigation | Decision status and reason, pause control, and supported thresholds |
| Zones | Valves, planned watering, and available soil readings |
| Automations | Run or stop a zone, stop all, pause or resume, and set overrides |
| Forecasts | Query a selected forecast model over a time window |

Entities depend on the server's configuration and available data. Missing measurements stay unavailable. Adding supported sources or zones updates the server's entity manifest.

[Entity and action guide →](https://localsky.io/docs/hacs)

## Use a forecast in an automation

`localsky.get_forecast_window` returns rain and temperature summaries with age and coverage information. Use `merged` for the forecast selected by LocalSky, or the ID of a configured extra model.

```yaml
action: localsky.get_forecast_window
data:
  track: merged
  start: "{{ now().replace(minute=0, second=0, microsecond=0).isoformat() }}"
  end: "{{ (now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)).isoformat() }}"
response_variable: forecast
```

This selects three hourly timestamps, including both ends. Check `complete`, `age_s`, and the particular summary values you need before acting. A missing rain value does not mean no rain.

[Forecast action details →](https://localsky.io/docs/hacs#forecast-window-action)

## Use HA weather sensors as LocalSky inputs

This integration publishes **LocalSky → HA**. To send existing HA weather sensors **HA → LocalSky**, configure **HA passthrough** in LocalSky's Devices settings.

You can keep HA's WeatherFlow integration and map its sensors into LocalSky. For its preceding-minute precipitation sensor, select **Rain last minute (accumulate today)**. [HA weather inputs →](https://localsky.io/docs/hacs#use-home-assistant-weather-sensors)

## Requirements

- Home Assistant **2024.11 or newer**.
- A reachable LocalSky server **0.7.0 or newer**, using API **1.12.0 through 2.x**.
- Forecast-window actions require server API **2.3.0 or newer**.

The current companion release is **0.9.3**. Use matching server and companion releases when updating.

### Need the server too?

| Your setup | Run LocalSky with |
|---|---|
| Home Assistant OS | [LocalSky app](https://github.com/silenthooligan/localsky-apps) |
| Home Assistant Container, or a separate host | [Docker](https://localsky.io/docs/getting-started) |

The app runs the server. The HACS integration adds its entities. You can use both together.

## Support

Report pairing, entity, and HA action problems [in this repository](https://github.com/silenthooligan/localsky-ha/issues). Report watering decisions, sources, and controller problems [in the main LocalSky repository](https://github.com/silenthooligan/localsky/issues).

[Documentation](https://localsky.io/docs/hacs) · [Latest release](https://github.com/silenthooligan/localsky-ha/releases/latest) · [Apache 2.0 license](LICENSE)
