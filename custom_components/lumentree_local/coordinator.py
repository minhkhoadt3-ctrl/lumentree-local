from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - Home Assistant runtime only
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
except ModuleNotFoundError:  # pragma: no cover - local/unit-test environment
    ConfigEntry = Any
    HomeAssistant = Any

    class DataUpdateCoordinator:  # type: ignore[no-redef]
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs) -> None:
            self.data = {}

        def async_set_updated_data(self, data):
            self.data = data

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LumentreeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Local MQTT coordinator. It keeps the latest payload and emits updates only when parser data arrives."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
        )
        self.entry = entry
        self.last_payload: dict[str, Any] = {}
        self.last_update: datetime | None = None
        self.device_state: dict[str, Any] = {}
        self.data: dict[str, Any] = {}

    def update_from_payload(self, payload: dict[str, Any]) -> None:
        """Accept parser output and publish it to Home Assistant without polling."""
        if not isinstance(payload, dict):
            _LOGGER.debug("Ignored non-dict payload for coordinator: %s", payload)
            return

        self.last_payload = payload
        self.last_update = datetime.now(timezone.utc)
        self.device_state = payload.copy()
        self.data = payload.copy()
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, Any]:
        """No polling; return the last known payload to keep the coordinator safe."""
        return self.data
