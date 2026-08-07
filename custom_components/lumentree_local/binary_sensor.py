from __future__ import annotations

from typing import Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, KEY_GRID_CONNECTED_STATUS
from .coordinator import LumentreeCoordinator

BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key=KEY_GRID_CONNECTED_STATUS,
        name="Grid Connected Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        # device_class.CONNECTIVITY sẽ hiển thị icon tự động: Connected (On) / Disconnected (Off)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities from config entry."""
    coordinator: LumentreeCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        LumentreeBinarySensor(coordinator, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class LumentreeBinarySensor(CoordinatorEntity[LumentreeCoordinator], BinarySensorEntity):
    """Binary sensor entity for Lumentree."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LumentreeCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        payload = self.coordinator.data or {}
        device_name = payload.get("device_name", payload.get("name", "Lumentree"))
        return DeviceInfo(
            identifiers={(DOMAIN, str(device_name))},
            name=str(device_name),
            manufacturer="Lumentree",
            model="Local",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            return None
        
        value = self.coordinator.data.get(self.entity_description.key)
        if value is None:
            return None

        # Xử lý linh hoạt các kiểu dữ liệu trả về từ coordinator/MQTT
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "on", "connected", "online")
        
        return False
