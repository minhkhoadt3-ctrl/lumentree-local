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
        
        # Lấy device_sn từ ConfigEntry để dùng trong update_from_payload
        self._device_sn = entry.data.get("device_sn")
        
        # Daily grid import energy accumulator
        self._daily_grid_in: dict[str, float] = {}
        self._last_grid_ts: dict[str, datetime] = {}
        self._grid_day: dict[str, date] = {}

    def update_from_payload(self, payload: dict) -> None:
        """Cập nhật dữ liệu sensor an toàn từ MQTT payload."""
        if not isinstance(payload, dict):
            return

        if self.data is None:
            self.data = {}

        data_to_update = payload

        # Nếu payload bị đóng gói dạng {"192.168.100.70:1886:...": {data}}
        if self._device_sn and self._device_sn in payload:
            data_to_update = payload[self._device_sn]
        else:
            # Tự động phát hiện nếu key đầu tiên là chuỗi IP/PORT (ví dụ: '192.168.100.70:1886:...')
            first_key = next(iter(payload.keys())) if payload else None
            if first_key and isinstance(first_key, str) and ":" in first_key and isinstance(payload[first_key], dict):
                data_to_update = payload[first_key]

        # Cập nhật dữ liệu mới vào coordinator
        if isinstance(data_to_update, dict):
            self.data.update(data_to_update)

        # BẮT BUỘC: Thông báo cho Home Assistant cập nhật trạng thái các sensor
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, Any]:
        """No polling; return the last known payload to keep the coordinator safe."""
        return self.data
