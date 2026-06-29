"""Small helpers shared across the LocalSky integration."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import LocalSkyCoordinator


def format_base_url(host: str, port: int, use_https: bool = False) -> str:
    """Return an HTTP(S) base URL that handles IPv6 hosts correctly.

    A bare IPv6 address (``::1``, ``fe80::1``) must be wrapped in square
    brackets when used as a URL authority, otherwise the port colon is
    ambiguous with the address colons. IPv4 and hostnames pass through
    unchanged. Already-bracketed input is preserved.
    """
    h = host.strip()
    scheme = "https" if use_https else "http"
    if h.startswith("[") and h.endswith("]"):
        authority = h
    elif ":" in h and not h.startswith("["):
        # Bare IPv6 literal. Drop any zone-id suffix for URL use; the IP
        # itself is enough for routing on a single LAN.
        bare = h.split("%", 1)[0]
        authority = f"[{bare}]"
    else:
        authority = h
    return f"{scheme}://{authority}:{port}"


# Sub-device grouping (Phase F2). LocalSky publishes one "LocalSky" hub device
# plus a sub-device per source group, so HA's device page mirrors LocalSky's
# own Device view (the Music-Assistant-style parity) instead of dumping every
# entity under a single device. The group is the entity's manifest `snapshot`
# ("tempest" | "irrigation" | "forecast"); anything else maps to the hub.
#
# The weather (tempest-snapshot) sub-device is intentionally NOT in this table:
# its name and model are driven by the source LocalSky actually reports
# (Tempest, Ecowitt, the source's config id, ...) so a cloud-only or Ecowitt
# user never gets a "LocalSky Tempest" device they do not own. See
# `_weather_device_label`.
_GROUP_LABELS: dict[str, tuple[str, str]] = {
    "irrigation": ("Irrigation", "Controller"),
    "forecast": ("Forecast", "Forecast service"),
}

# Neutral fallback for the weather sub-device when LocalSky has not reported a
# source label yet (no reading received, or an older server that omits it).
_WEATHER_FALLBACK_NAME = "LocalSky Weather"
_WEATHER_FALLBACK_MODEL = "Weather source"


def _weather_device_label(coordinator: "LocalSkyCoordinator | None") -> tuple[str, str]:
    """(name, model) for the tempest-snapshot sub-device, from the live source.

    LocalSky's tempest snapshot carries `source_label` — the display name of
    the source currently driving current conditions ("Tempest", "Ecowitt", the
    source's config id, "Demo", ...). We surface that so the HA device matches
    the hardware the user actually runs, falling back to a neutral name before
    the first reading arrives or when the field is absent.
    """
    snapshot = (getattr(coordinator, "data", None) or {}).get("tempest") or {}
    label = snapshot.get("source_label")
    if isinstance(label, str) and label.strip():
        label = label.strip()
        return f"LocalSky {label}", f"{label} weather source"
    return _WEATHER_FALLBACK_NAME, _WEATHER_FALLBACK_MODEL


def device_info_for(
    entry: ConfigEntry,
    coordinator: "LocalSkyCoordinator | None",
    group: str | None = None,
) -> DeviceInfo:
    """DeviceInfo for an entity, grouped into a sub-device by `group`.

    `group=None` (or an unknown group) returns the top-level LocalSky hub.
    A known group returns a sub-device linked to the hub via `via_device`,
    so HA renders LocalSky -> {Weather, Irrigation, Forecast}. The weather
    sub-device's name/model follow the source LocalSky reports rather than
    assuming a Tempest station.
    """
    hub = (DOMAIN, entry.entry_id)
    info = getattr(coordinator, "info", None)
    base_url = format_base_url(
        entry.data.get("host", ""),
        entry.data.get("port", 8090),
        entry.data.get("use_https", False),
    )
    if group == "tempest":
        name, model = _weather_device_label(coordinator)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_tempest")},
            name=name,
            manufacturer="LocalSky",
            model=model,
            via_device=hub,
            configuration_url=base_url,
        )
    if not group or group not in _GROUP_LABELS:
        return DeviceInfo(
            identifiers={hub},
            name="LocalSky",
            manufacturer="LocalSky",
            model="LocalSky Service",
            sw_version=(info or {}).get("service_version", "unknown"),
            configuration_url=base_url,
        )
    name, model = _GROUP_LABELS[group]
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{group}")},
        name=f"LocalSky {name}",
        manufacturer="LocalSky",
        model=model,
        via_device=hub,
        configuration_url=base_url,
    )
