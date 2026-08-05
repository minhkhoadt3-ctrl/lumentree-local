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
        
        # Lấy device_sn từ ConfigEntry
        self._device_sn = entry.data.get("device_sn") or entry.entry_id
        
        # Daily grid energy accumulator
        self._daily_grid_in: float = 0.0
        self._last_grid_ts: datetime | None = None
        self._grid_day: date | None = None

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
            first_key = next(iter(payload.keys())) if payload else None
            if first_key and isinstance(first_key, str) and ":" in first_key and isinstance(payload[first_key], dict):
                data_to_update = payload[first_key]

        # Cập nhật dữ liệu mới vào coordinator
        if isinstance(data_to_update, dict):
            self.data.update(data_to_update)

           # --- TÍNH TOÁN TÍCH LŨY LƯỚI TRONG NGÀY ---
            now = dt_util.now()

            # 1. Kiểm tra chuyển ngày
            if self._grid_day is None:
                # Nếu lần đầu nhận MQTT packet: Chỉ ghi nhận ngày, KHÔNG đè _daily_grid_in về 0
                self._grid_day = now.date()
                self._last_grid_ts = now
            elif self._grid_day != now.date():
                # Chỉ khi thực sự bước sang ngày mới (sau 00:00 AM) mới reset về 0
                self._grid_day = now.date()
                self._daily_grid_in = 0.0
                self._last_grid_ts = now

            # Tích lũy toàn bộ công suất lưới (dùng abs để lấy cả chiều âm lẫn dương)
            grid_power = data_to_update.get(KEY_GRID_POWER)
            if grid_power is not None and self._last_grid_ts is not None:
                time_diff = (now - self._last_grid_ts).total_seconds()
                # Chỉ tính khi khoảng thời gian hợp lý (dưới 10 phút)
                if 0 < time_diff < 600:
                    # Dùng abs(grid_power) để tính tổng công suất trao đổi với lưới
                    energy_kwh = (abs(grid_power) * time_diff) / 3600000.0
                    self._daily_grid_in += energy_kwh
            
            self._last_grid_ts = now

            # Ghi đè/Cập nhật giá trị tính toán vào key năng lượng ngày
            self.data[KEY_DAILY_GRID_IN_KWH] = round(self._daily_grid_in, 3)

        # BẮT BUỘC: Thông báo cho Home Assistant cập nhật trạng thái các sensor
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, Any]:
        """No polling; return the last known payload to keep the coordinator safe."""
        return self.data
