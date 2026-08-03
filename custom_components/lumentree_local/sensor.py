from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BATTERY,
    ATTR_DEVICE_NAME,
    ATTR_HUMIDITY,
    ATTR_POWER,
    ATTR_TEMPERATURE,
    DOMAIN,
    KEY_AC_IN_CURRENT,
    KEY_AC_OUT_CURRENT,
    KEY_AC_OUT_FREQ,
    KEY_AC_OUT_POWER,
    KEY_AC_OUT_VA,
    KEY_AC_OUT_VOLTAGE,
    KEY_BATTERY_CURRENT,
    KEY_BATTERY_POWER,
    KEY_BATTERY_SOC,
    KEY_BATTERY_VOLTAGE,
    KEY_DAILY_CHARGE_KWH,
    KEY_DAILY_DISCHARGE_KWH,
    KEY_DAILY_ESSENTIAL_KWH,
    KEY_DAILY_LOAD_KWH,
    KEY_DAILY_PV_KWH,
    KEY_DAILY_TOTAL_LOAD_KWH,
    KEY_DAILY_GRID_IN_KWH,
    KEY_DEVICE_TEMP,
    KEY_GRID_POWER,
    KEY_LOAD_POWER,
    KEY_MONTHLY_GRID_IN_KWH,
    KEY_MPPT_TEMP,
    KEY_PV1_CURRENT,
    KEY_PV1_POWER,
    KEY_PV1_VOLTAGE,
    KEY_PV2_POWER,
    KEY_TOTAL_LOAD_POWER,
)
from .coordinator import LumentreeCoordinator

REALTIME_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=KEY_BATTERY_POWER,
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key=KEY_DAILY_GRID_IN_KWH,
        translation_key="daily_grid_in",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:transmission-tower-import",
    ),
    SensorEntityDescription(
        key=KEY_PV2_POWER,
        name="PV2 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        #entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_AC_OUT_VA,
        name="AC Output Apparent Power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=KEY_MONTHLY_GRID_IN_KWH,
        name="Grid Input Today1",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-import",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_GRID_POWER,
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_LOAD_POWER,
        name="Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug",
    ),
    SensorEntityDescription(
        key=KEY_AC_OUT_POWER,
        name="AC Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=KEY_AC_OUT_CURRENT,
        name="AC Out Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_TOTAL_LOAD_POWER,
        name="Total Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug-outline",
    ),
    SensorEntityDescription(
        key=KEY_PV1_POWER,
        name="PV1 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        #entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_PV1_CURRENT,
        name="PV1 Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-dc",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_VOLTAGE,
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-outline",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_AC_OUT_VOLTAGE,
        name="AC Output Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_AC_IN_CURRENT,
        name="EVN Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_PV1_VOLTAGE,
        name="PV1 Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        #entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_CURRENT,
        name="Battery Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-dc",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_AC_OUT_FREQ,
        name="AC Output Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_BATTERY_SOC,
        name="Battery SOC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=KEY_DEVICE_TEMP,
        name="Device Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_MPPT_TEMP,
        name="MPPT Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_PV_KWH,
        name="PV Generation Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_CHARGE_KWH,
        name="Battery Charge Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-plus-variant",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_DISCHARGE_KWH,
        name="Battery Discharge Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-minus-variant",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_LOAD_KWH,
        name="Load Consumption Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:home-lightning-bolt",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_ESSENTIAL_KWH,
        name="Essential Load Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:power-plug",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_DAILY_TOTAL_LOAD_KWH,
        name="Total Load Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt-circle",
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(hass, config_entry, async_add_entities,):
    """Set up sensor entities from the config entry."""
    coordinator: LumentreeCoordinator = hass.data[DOMAIN][config_entry.entry_id]      
    
    async_add_entities(
        LumentreeSensor(coordinator, desc)
        for desc in REALTIME_SENSOR_DESCRIPTIONS
    )


class LumentreeSensor(CoordinatorEntity[LumentreeCoordinator], SensorEntity):
    """Sensor entity reflecting local device state."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LumentreeCoordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        payload = self.coordinator.data
        device_name = payload.get("device_name", payload.get("name", "Lumentree"))
        return DeviceInfo(
            identifiers={(DOMAIN, device_name)},
            name=str(device_name),
            manufacturer="Lumentree",
            model="Local",
        )

    @property
    def native_value(self):
        payload = self.coordinator.data
        return payload.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data)

    @property
    def should_poll(self) -> bool:
        return False

    async def async_update(self) -> None:
        """No polling: entity state is refreshed only when MQTT parser pushes new data."""
        return None
