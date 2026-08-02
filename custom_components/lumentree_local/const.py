from __future__ import annotations

from typing import Final

DOMAIN: Final = "lumentree_local"
PLATFORMS: Final = ["sensor"]

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_SN: Final = "device_sn"
CONF_DEVICE_ID: Final = "device_id"
CONF_POLLING: Final = "polling"
CONF_TOPIC: Final = "topic"

DEFAULT_PORT: Final = 1886
DEFAULT_POLLING: Final = 4
DEFAULT_TOPIC: Final = "reportApp/+/+"
DEFAULT_POLLING_INTERVAL: Final = 4
MQTT_BROKER: Final = "192.168.100.70"
MQTT_PORT: Final = DEFAULT_PORT
MQTT_USERNAME: Final = ""
MQTT_PASSWORD: Final = ""
MQTT_KEEPALIVE: Final = 60
MQTT_CLIENT_ID_FORMAT: Final = "ha-lumentree-{device_id}-{timestamp}"
MQTT_SUB_TOPIC_FORMAT: Final = "reportApp/{device_sn}"
MQTT_PUB_TOPIC_FORMAT: Final = "listenApp/{device_sn}"
SIGNAL_UPDATE_FORMAT: Final = "lumentree_local_update_{device_sn}"

ATTR_DEVICE_NAME: Final = "device_name"
ATTR_BATTERY: Final = "battery"
ATTR_TEMPERATURE: Final = "temperature"
ATTR_HUMIDITY: Final = "humidity"
ATTR_POWER: Final = "power"
ATTR_FIRMWARE: Final = "firmware"
ATTR_SIGNAL: Final = "signal"

KEY_ONLINE_STATUS: Final = "online_status"
KEY_LAST_RAW_MQTT: Final = "last_raw_mqtt"
KEY_BATTERY_POWER: Final = "battery_power"
KEY_BATTERY_SOC: Final = "battery_soc"
KEY_GRID_POWER: Final = "grid_power"
KEY_LOAD_POWER: Final = "load_power"
KEY_BATTERY_VOLTAGE: Final = "battery_voltage"
KEY_BATTERY_CURRENT: Final = "battery_current"
KEY_AC_OUT_VOLTAGE: Final = "ac_out_voltage"
KEY_AC_OUT_FREQ: Final = "ac_out_freq"
KEY_AC_OUT_FREQUENCY: Final = KEY_AC_OUT_FREQ
KEY_AC_OUT_POWER: Final = "ac_out_power"
KEY_AC_OUT_CURRENT: Final = "ac_out_current"
KEY_AC_OUT_VA: Final = "ac_out_va"
KEY_DEVICE_TEMP: Final = "device_temp"
KEY_MPPT_TEMP: Final = "mppt_temp"
KEY_PV1_VOLTAGE: Final = "pv1_voltage"
KEY_PV1_POWER: Final = "pv1_power"
KEY_PV2_POWER: Final = "pv2_power"
KEY_AC_IN_POWER: Final = "ac_in_power"
KEY_AC_IN_CURRENT: Final = "ac_in_current"
KEY_FW_VERSION: Final = "fw_version"
KEY_CTRL_VERSION: Final = "ctrl_version"
KEY_PV1_CURRENT: Final = "pv1_current"
KEY_MQTT_DEVICE_SN: Final = "mqtt_device_sn"
KEY_DAILY_PV_KWH: Final = "daily_pv_kwh"
KEY_DAILY_CHARGE_KWH: Final = "daily_charge_kwh"
KEY_DAILY_DISCHARGE_KWH: Final = "daily_discharge_kwh"
KEY_DAILY_LOAD_KWH: Final = "daily_load_kwh"
KEY_DAILY_ESSENTIAL_KWH: Final = "daily_essential_kwh"
KEY_DAILY_TOTAL_LOAD_KWH: Final = "daily_total_load_kwh"
KEY_MONTHLY_GRID_IN_KWH: Final = "monthly_grid_in_kwh"
KEY_MONTHLY_LOAD_KWH: Final = "monthly_load_kwh"
KEY_MONTHLY_ESSENTIAL_KWH: Final = "monthly_essential_kwh"
KEY_TOTAL_LOAD_POWER: Final = "total_load_power"

REG_ADDR: Final = {
    "FIRMWARE_VERSION": 2,
    "DEVICE_MODEL_START": 3,
    "CONTROLLER_VERSION": 8,
    "BATTERY_VOLTAGE": 11,
    "BATTERY_CURRENT": 12,
    "AC_OUT_VOLTAGE": 13,
    "GRID_VOLTAGE": 15,
    "AC_OUT_FREQ": 16,
    "AC_IN_FREQ": 17,
    "AC_OUT_POWER": 18,
    "PV1_VOLTAGE": 20,
    "PV1_CURRENT": 21,
    "PV1_POWER": 22,
    "DEVICE_TEMP": 24,
    "MPPT_TEMP": 25,
    "DAILY_PV_KWH": 33,
    "BATTERY_TYPE": 37,
    "DAILY_CHARGE_KWH": 41,
    "DAILY_DISCHARGE_KWH": 42,
    "DAILY_ESSENTIAL_KWH": 47,
    "BATTERY_SOC": 50,
    "AC_IN_POWER": 53,
    "AC_IN_CURRENT": 54,
    "GRID_POWER": 59,
    "BATTERY_POWER": 61,
    "AC_OUT_CURRENT": 62,
    "AC_OUT_VA": 63,
    "LOAD_POWER": 67,
    "UPS_MODE": 68,
    "DAILY_LOAD_KWH": 69,
    "MASTER_SLAVE_STATUS": 70,
    "PV2_VOLTAGE": 72,
    "PV2_POWER": 60,
    "MONTHLY_GRID_IN_KWH": 34,
    "MONTHLY_LOAD_KWH": 51,
    "MONTHLY_ESSENTIAL_KWH": 64,
}
REG_ADDR_CELL_START: Final = 0
REG_ADDR_CELL_COUNT: Final = 0
