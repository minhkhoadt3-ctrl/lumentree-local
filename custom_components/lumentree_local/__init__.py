from __future__ import annotations

from typing import Any

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
except ModuleNotFoundError:  # pragma: no cover - used when the package is imported outside HA runtime
    ConfigEntry = Any
    HomeAssistant = Any

from .const import CONF_DEVICE_SN, DOMAIN, PLATFORMS

try:  # pragma: no cover - only exists in Home Assistant runtime
    from .coordinator import LumentreeCoordinator
    from .mqtt_client import LumentreeMqttClient
except ModuleNotFoundError:  # pragma: no cover - used by tests / local tooling
    LumentreeCoordinator = None
    LumentreeMqttClient = None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the component from YAML configuration if needed."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the component from a config entry without polling."""
    if LumentreeCoordinator is None or LumentreeMqttClient is None:
        raise RuntimeError("Home Assistant is required to set up this integration")

    coordinator = LumentreeCoordinator(hass, entry)
    device_sn = str(entry.data.get(CONF_DEVICE_SN, entry.title or "lumentree")).strip() or "lumentree"

    mqtt_client = LumentreeMqttClient(
        hass,
        entry,
        device_sn=device_sn,
        device_id=entry.entry_id,
        callback=coordinator.update_from_payload,
    )
    mqtt_client.subscribe(mqtt_client.topic_subs)
    coordinator.mqtt_client = mqtt_client

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN][f"{entry.entry_id}_mqtt"] = mqtt_client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await mqtt_client.connect()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        mqtt_client = hass.data.get(DOMAIN, {}).get(f"{entry.entry_id}_mqtt")
        if mqtt_client is not None:
            await mqtt_client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_mqtt", None)
    return unload_ok
