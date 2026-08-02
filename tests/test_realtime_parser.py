from __future__ import annotations

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
