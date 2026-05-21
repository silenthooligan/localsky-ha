"""Small helpers shared across the LocalSky integration."""
from __future__ import annotations


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
