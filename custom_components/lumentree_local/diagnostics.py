from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for the config entry, including MQTT and latency details."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diagnostics = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": dict(entry.data),
        "options": dict(entry.options),
        "last_mqtt": getattr(coordinator, "last_mqtt", None),
        "last_packet": getattr(coordinator, "last_packet", None),
        "last_poll": getattr(coordinator, "last_poll", None),
        "signal": getattr(coordinator, "signal", None),
        "client_id": getattr(coordinator, "client_id", None),
        "latency": getattr(coordinator, "latency", None),
    }

    return diagnostics
