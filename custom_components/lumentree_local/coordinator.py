from __future__ import annotations

import logging
from datetime import datetime, timezone, date
from homeassistant.util import dt as dt_util
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

from .const import (
    DOMAIN,
    KEY_GRID_POWER,
    KEY_MQTT_DEVICE_SN,
    KEY_DAILY_GRID_IN_KWH,
)

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
        
        # Daily grid import energy accumulator
        self._daily_grid_in: dict[str, float] = {}
        self._last_grid_ts: dict[str, datetime] = {}
        self._grid_day: dict[str, date] = {}

    def update_from_payload(self, payload: dict[str, Any]) -> None:
        """Accept parser output and publish it to Home Assistant without polling."""
        if not isinstance(payload, dict):
            _LOGGER.debug("Ignored non-dict payload for coordinator: %s", payload)
            return

        self.last_payload = payload
        self.last_update = dt_util.now()
        data = payload.copy()

        # Calculate daily grid import energy (kWh)
        device_id = data.get(KEY_MQTT_DEVICE_SN)
        grid_power = data.get(KEY_GRID_POWER)

        if device_id and grid_power is not None:
            now = dt_util.now()

            if device_id not in self._daily_grid_in:
                self._daily_grid_in[device_id] = 0.0
                self._last_grid_ts[device_id] = now
                self._grid_day[device_id] = now.date()

            # reset at new day
            if now.date() != self._grid_day[device_id]:
                self._daily_grid_in[device_id] = 0.0
                self._grid_day[device_id] = now.date()

            dt = (now - self._last_grid_ts[device_id]).total_seconds()
            self._last_grid_ts[device_id] = now

            if dt > 0:
                self._daily_grid_in[device_id] += (
                    abs(float(grid_power)) * dt / 3600000
                )

            data[KEY_DAILY_GRID_IN_KWH] = round(
                self._daily_grid_in[device_id],
                3,
            )
        self.device_state = payload.copy()
        self.data = payload.copy()
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, Any]:
        """No polling; return the last known payload to keep the coordinator safe."""
        return self.data
