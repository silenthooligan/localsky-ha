<h1 align="center">LocalSky for Home Assistant</h1>

<p align="center">
  <strong>Home Assistant integration for <a href="https://github.com/silenthooligan/localsky">LocalSky</a>.</strong><br>
  Local-polling. Config flow. No YAML.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache_2.0-3b82f6.svg"></a>
  <a href="https://github.com/hacs/integration"><img alt="HACS" src="https://img.shields.io/badge/HACS-Custom-orange.svg"></a>
  <a href="https://www.home-assistant.io/"><img alt="HA 2024.4+" src="https://img.shields.io/badge/Home_Assistant-2024.4+-blue.svg"></a>
</p>

This integration turns a running [LocalSky](https://github.com/silenthooligan/localsky) instance into a first-class Home Assistant device. Every sensor that LocalSky's dashboard surfaces becomes a HA entity, and each zone exposes a switch you can drive from automations.

LocalSky itself runs as a separate service (one Docker container on your LAN). This is just the thin Python client that exposes its REST API to HA.

## What you get

Per LocalSky instance, the integration creates one device with:

| Kind | Entities |
|---|---|
| Weather (`sensor`) | air temp, feels like, humidity, dew point, wind speed, wind gust, pressure, rain today, solar irradiance, UV index |
| Verdict (`sensor`) | today's run / skip verdict from the engine |
| Per zone (`sensor`) | soil bucket (mm), planned-run seconds, minutes run today |
| Per zone (`binary_sensor`) | running on/off |
| Any zone (`binary_sensor`) | true when any zone is running |
| Per zone (`switch`) | turn on = run for 10 min; turn off = stop |

All values come from LocalSky's `/api/v1/snapshot`, `/api/v1/irrigation/snapshot`, and `/api/v1/forecast/snapshot` endpoints, polled every 30 seconds.

## Install via HACS (custom repository)

1. In Home Assistant, open **HACS** -> **Integrations**.
2. Open the three-dot menu (top right) -> **Custom repositories**.
3. Add `https://github.com/silenthooligan/localsky-hacs` with category **Integration**.
4. Search for **LocalSky** in HACS and install.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & Services -> Add Integration** and search for **LocalSky**.
7. Enter the LocalSky host (e.g. `192.168.1.100`) and port (default `8090`).

## Install manually

```bash
# from your HA config dir
git clone https://github.com/silenthooligan/localsky-hacs.git
cp -r localsky-hacs/custom_components/localsky custom_components/
# restart HA, then add the integration from the UI
```

## Multi-instance

You can pair a single HA install against multiple LocalSky instances (test-bed + production, or one per house). Each `host:port` becomes its own config entry and device. Entity names include the LocalSky's device label so they don't collide.

## Requirements

- Home Assistant **2024.4.0** or newer.
- A reachable LocalSky service running **0.2.0** or newer (the integration probes `/api/v1/info` and refuses to set up against older instances).

## Status

Tier-1 custom HACS repository. Submission to the HACS default catalog is gated on:

- 90 days of low-issue-volume soak via the custom-repo install path.
- LocalSky's REST API confirmed stable at `/api/v1/*`.
- Unit tests against `pytest-homeassistant-custom-component`.

See the [LocalSky HACS roadmap](https://github.com/silenthooligan/localsky/blob/main/docs/hacs.md) on the main repo for the gating criteria.

## Contributing

Bug reports and PRs welcome. For LocalSky-side issues (engine logic, source adapters, controller HAL), file against the main [silenthooligan/localsky](https://github.com/silenthooligan/localsky) repo. For HA-integration issues (config flow, entity shape, polling), file here.

## License

Apache-2.0. See [LICENSE](LICENSE).
