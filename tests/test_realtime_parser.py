from __future__ import annotations

import logging

from custom_components.lumentree_local.mqtt_client import LumentreeMqttClient
from custom_components.lumentree_local.realtime_parser import parse_mqtt_payload, parse_realtime_payload


def test_parse_realtime_payload_maps_common_fields():
    payload = {
        "device_name": "Lumentree-01",
        "battery_soc": 76,
        "grid_power": 1200,
        "load_power": 400,
        "battery_voltage": 53.2,
        "temperature": 28.5,
    }

    result = parse_realtime_payload(payload)

    assert result["device_name"] == "Lumentree-01"
    assert result["battery"] == 76
    assert result["power"] == 1200
    assert result["temperature"] == 28.5


def test_parse_mqtt_payload_accepts_json_string():
    raw = '{"device_name":"LT-02","battery_soc":88,"power":3500}'

    result = parse_mqtt_payload(raw)

    assert result is not None
    assert result["device_name"] == "LT-02"
    assert result["battery"] == 88
    assert result["power"] == 3500


def test_parse_mqtt_payload_accepts_real_device_frames():
    listen_payload = "301e00146c697374656e4170702f48323431323035303737010300000046c438"
    report_payload = "30b30100147265706f72744170702f48323431323035303737010300000046c4382b2b2b2b01038c0300011501024832343132303530373700071265122414f0055a09560000096013741374023f000000150000000000000553057c000000000000000000000000000000caffbd000000000001000000000000005300580000000000000000006b00000000004400010000ffa4ff240000000000960000000b000102e300e202ad00ba0000000000670001004602de"

    listen_result = parse_mqtt_payload(listen_payload)
    report_result = parse_mqtt_payload(report_payload)

    assert listen_result is not None
    assert listen_result["device_name"] == "H241205077"
    assert listen_result["source"] == "listenApp"

    assert report_result is not None
    assert report_result["device_name"] == "H241205077"
    assert report_result["source"] == "reportApp"


def test_mqtt_clean_disconnect_does_not_log_unexpected_warning(caplog):
    client = object.__new__(LumentreeMqttClient)
    for slot_name in LumentreeMqttClient.__slots__:
        if slot_name == "hass":
            client.hass = type(
                "HassStub",
                (),
                {"loop": type("LoopStub", (), {"call_soon_threadsafe": staticmethod(lambda cb: cb())})()},
            )()
        elif slot_name == "_client_id":
            object.__setattr__(client, "_client_id", "ha-test-client")
        elif slot_name == "_is_connected":
            object.__setattr__(client, "_is_connected", True)
        elif slot_name == "_stopping":
            object.__setattr__(client, "_stopping", True)
        elif slot_name == "_offline_timer_unsub":
            object.__setattr__(client, "_offline_timer_unsub", None)
        elif slot_name == "_offline_timer_gen":
            object.__setattr__(client, "_offline_timer_gen", 0)
        elif slot_name == "_online":
            object.__setattr__(client, "_online", False)
        elif slot_name == "_topic_subs":
            object.__setattr__(client, "_topic_subs", ("reportApp/H241205077",))

    with caplog.at_level(logging.WARNING):
        client._on_disconnect(None, None, 0)

    assert "unexpected disconnect" not in caplog.text.lower()


def test_realtime_sensor_keys_are_defined():
    from custom_components.lumentree_local.const import (
        KEY_AC_OUT_VA,
        KEY_BATTERY_POWER,
        KEY_BATTERY_SOC,
        KEY_DAILY_PV_KWH,
        KEY_GRID_POWER,
    )

    assert KEY_BATTERY_POWER == "battery_power"
    assert KEY_GRID_POWER == "grid_power"
    assert KEY_BATTERY_SOC == "battery_soc"
    assert KEY_AC_OUT_VA == "ac_out_va"
    assert KEY_DAILY_PV_KWH == "daily_pv_kwh"


def test_register_map_uses_real_lumentree_addresses():
    from custom_components.lumentree_local.const import REG_ADDR

    assert REG_ADDR["BATTERY_VOLTAGE"] == 11
    assert REG_ADDR["BATTERY_CURRENT"] == 12
    assert REG_ADDR["AC_OUT_VOLTAGE"] == 13
    assert REG_ADDR["AC_OUT_FREQ"] == 16
    assert REG_ADDR["AC_OUT_POWER"] == 18
    assert REG_ADDR["PV1_VOLTAGE"] == 20
    assert REG_ADDR["PV1_CURRENT"] == 21
    assert REG_ADDR["PV1_POWER"] == 22
    assert REG_ADDR["BATTERY_SOC"] == 50
    assert REG_ADDR["GRID_POWER"] == 59
    assert REG_ADDR["BATTERY_POWER"] == 61
    assert REG_ADDR["AC_OUT_CURRENT"] == 62
    assert REG_ADDR["AC_OUT_VA"] == 63
    assert REG_ADDR["LOAD_POWER"] == 67
    assert REG_ADDR["DAILY_LOAD_KWH"] == 69
    assert REG_ADDR["MONTHLY_GRID_IN_KWH"] == 34
