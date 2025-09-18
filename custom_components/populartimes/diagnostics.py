"""Diagnostics support for Popular Times.

Allows downloading anonymized diagnostics for a config entry from the UI.
This is safe and does not change runtime behavior.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _redact_address(address: str | None) -> str | None:
    """Return a lightly redacted address for diagnostics (avoid full PII)."""
    if not address:
        return address
    # Keep city/state/country hints, redact street/number parts conservatively
    parts = [p.strip() for p in address.split(",")]
    if not parts:
        return address
    # Redact first segment which typically contains house number/street
    parts[0] = "***"
    return ", ".join(parts)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a given config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    # Read configured values (options preferred), redact address
    name = entry.options.get("name", entry.data.get("name"))
    addr = entry.options.get("address", entry.data.get("address"))

    diag: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "domain": entry.domain,
            "source": entry.source,
        },
        "config": {
            "name": name,
            "address_redacted": _redact_address(addr),
        },
    }

    if coordinator is not None:
        diag["coordinator"] = {
            "name": getattr(coordinator, "name", None),
            "update_interval": str(getattr(coordinator, "update_interval", None)),
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "last_update_success_time": str(
                getattr(coordinator, "last_update_success_time", None)
            ),
            "last_exception": repr(getattr(coordinator, "last_exception", None))
            if getattr(coordinator, "last_exception", None)
            else None,
            # Include a compact view of current data
            "data": getattr(coordinator, "data", None),
        }

    return diag
