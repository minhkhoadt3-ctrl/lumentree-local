from __future__ import annotations

import json
import logging
import math
import re
import struct
from typing import Any, Mapping, Optional

try:
    import crcmod.predefined
except ModuleNotFoundError:  # pragma: no cover - optional dependency for local/test environments
    crcmod = None

from .const import (
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
    KEY_DEVICE_TEMP,
    KEY_GRID_POWER,
    KEY_LOAD_POWER,
    KEY_MQTT_DEVICE_SN,
    KEY_MPPT_TEMP,
    KEY_MONTHLY_ESSENTIAL_KWH,
    KEY_MONTHLY_GRID_IN_KWH,
    KEY_MONTHLY_LOAD_KWH,
    KEY_PV1_CURRENT,
    KEY_PV1_POWER,
    KEY_PV1_VOLTAGE,
    KEY_PV2_POWER,
)

_LOGGER = logging.getLogger(__name__)

crc16_modbus_func = crcmod.predefined.mkCrcFun("modbus") if crcmod is not None else None

_STRUCT_FORMATS: dict[str, struct.Struct] = {
    "signed_2": struct.Struct(">h"),
    "unsigned_2": struct.Struct(">H"),
    "signed_4": struct.Struct(">i"),
    "unsigned_4": struct.Struct(">I"),
}


def calculate_crc16_modbus(pb: bytes) -> Optional[int]:
    if crc16_modbus_func:
        try:
            return crc16_modbus_func(pb)
        except Exception:
            return None
    return None


def verify_crc(ph: str) -> tuple[bool, Optional[str]]:
    if not crc16_modbus_func:
        return True, "CRC skipped"
    if len(ph) < 4:
        return False, "Too short"
    try:
        dh, rc = ph[:-4], ph[-4:].lower()
        db = bytes.fromhex(dh)
        cc = calculate_crc16_modbus(db)
        if cc is None:
            return False, "Calc fail"
        cch = cc.to_bytes(2, "little").hex()
        ok = cch == rc
        return ok, None if ok else f"Mismatch {rc} vs {cch}"
    except Exception:
        return False, "Verify error"


def generate_modbus_read_command(sid: int, fc: int, addr: int, num: int) -> Optional[str]:
    try:
        pdu = bytearray([fc]) + addr.to_bytes(2, "big") + num.to_bytes(2, "big")
        adu = bytearray([sid]) + pdu
        crc = calculate_crc16_modbus(bytes(adu))
        if crc is None:
            return None
        full = adu + crc.to_bytes(2, "little")
        return full.hex()
    except Exception:
        return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _decode_payload(payload: str | bytes | bytearray) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            _LOGGER.debug("Unable to decode MQTT payload bytes as UTF-8")
            return None

    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return None
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return payload

    return payload


def _read_register(db: bytes, ra: int, signed: bool, factor: float = 1.0, byte_count: int = 2) -> Optional[float]:
    offset_bytes = ra * 2
    if offset_bytes + byte_count > len(db):
        return None
    try:
        raw_bytes = db[offset_bytes : offset_bytes + byte_count]
        if byte_count == 2:
            fmt = _STRUCT_FORMATS["signed_2"] if signed else _STRUCT_FORMATS["unsigned_2"]
        elif byte_count == 4:
            fmt = _STRUCT_FORMATS["signed_4"] if signed else _STRUCT_FORMATS["unsigned_4"]
        else:
            return None
        raw_val = fmt.unpack(raw_bytes)[0]
        result = round(raw_val * factor, 3)
        if not math.isfinite(result):
            return None
        return result
    except struct.error:
        return None
    except Exception:
        return None


def _read_string(db: bytes, sa: int, nr: int) -> Optional[str]:
    offset = sa * 2
    num_bytes = nr * 2
    if offset + num_bytes > len(db):
        return None
    try:
        raw_bytes = db[offset : offset + num_bytes]
        return raw_bytes.decode("ascii", "ignore").replace("\x00", "").strip() or None
    except Exception:
        return None


def _parse_device_frame(payload_hex: str) -> dict[str, Any] | None:
    """Parse the real Lumentree MQTT binary framing used by the device."""
    if not payload_hex:
        return None

    try:
        data = bytes.fromhex(payload_hex)
    except ValueError:
        return None

    if len(data) < 12:
        return None

    # The real payload contains ASCII markers such as "reportApp/H241205077" or
    # "listenApp/H241205077" embedded in the binary stream. The length field is
    # not at a fixed offset across both packet types, so detect the path text directly.
    text = data.decode("latin1")
    match = re.search(r"(listenApp|reportApp)/([A-Za-z0-9]+)", text)
    if not match:
        # Fallback for exception cases: use the legacy length-field pattern.
        for offset in range(0, min(len(data) - 4, 12)):
            if data[offset : offset + 2] == b"\x00\x14":
                path_len = int.from_bytes(data[offset : offset + 2], byteorder="big", signed=False)
                candidate = data[offset + 2 : offset + 2 + path_len]
                try:
                    candidate_text = candidate.decode("ascii")
                except UnicodeDecodeError:
                    continue
                if "/" in candidate_text:
                    source, device_name = candidate_text.split("/", 1)
                    return {
                        "source": source,
                        "device_name": device_name,
                        "online": True,
                        "raw_hex": payload_hex,
                    }
        return None

    source = match.group(1)
    device_name = match.group(2)
    return {
        "source": source,
        "device_name": device_name,
        "online": True,
        "raw_hex": payload_hex,
    }


def parse_realtime_payload(payload: dict[str, Any] | str | bytes | None) -> dict[str, Any]:
    if payload is None:
        return {}

    decoded = _decode_payload(payload)
    if decoded is None:
        return {}

    if isinstance(decoded, str):
        stripped = decoded.strip()
        if not stripped:
            return {}
        if "listenApp/" in stripped or "reportApp/" in stripped:
            match = re.search(r"(listenApp|reportApp)/([A-Za-z0-9]+)", stripped)
            if match:
                source = match.group(1)
                device_name = match.group(2)
                _LOGGER.debug("Detected ascii MQTT route payload: %s/%s", source, device_name)
                return {"source": source, "device_name": device_name, "online": True, "raw_hex": stripped}
        if len(stripped) >= 8 and all(ch in "0123456789abcdefABCDEF" for ch in stripped):
            parsed = _parse_device_frame(stripped)
            if parsed is not None:
                _LOGGER.debug("Detected device MQTT binary frame: %s", parsed)
                return parsed
            _LOGGER.debug("Detected raw hex MQTT payload; storing raw payload without decoding register values")
            return {"device_name": "Lumentree", "raw_hex": stripped}
        _LOGGER.debug("Ignoring non-JSON MQTT payload: %s", stripped)
        return {}

    if not isinstance(decoded, Mapping):
        raise ValueError("Realtime payload must be a mapping or JSON string")

    payload_map = dict(decoded)
    device_name = _coalesce(
        payload_map.get("device_name"),
        payload_map.get("name"),
        payload_map.get("device"),
        "Lumentree",
    )

    battery = _coalesce(
        payload_map.get("battery_soc"),
        payload_map.get("battery"),
        payload_map.get("soc"),
    )
    temperature = _coalesce(
        payload_map.get("temperature"),
        payload_map.get("device_temp"),
        payload_map.get("temp"),
    )
    humidity = _coalesce(
        payload_map.get("humidity"),
        payload_map.get("relative_humidity"),
    )
    power = _coalesce(
        payload_map.get("power"),
        payload_map.get("ac_out_power"),
        payload_map.get("grid_power"),
        payload_map.get("load_power"),
    )

    normalized = {
        "device_name": str(device_name),
        "battery": battery,
        "temperature": temperature,
        "humidity": humidity,
        "power": power,
    }

    _LOGGER.debug("Parsed realtime payload: %s", normalized)
    return normalized


def parse_mqtt_payload(payload: str | bytes | bytearray | dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None

    if isinstance(payload, Mapping):
        return parse_realtime_payload(dict(payload))

    decoded = _decode_payload(payload)
    if decoded is None:
        return None
    if isinstance(decoded, Mapping):
        return parse_realtime_payload(decoded)
    if isinstance(decoded, str):
        stripped = decoded.strip()
        if not stripped:
            return None
        if "listenApp/" in stripped or "reportApp/" in stripped:
            match = re.search(r"(listenApp|reportApp)/([A-Za-z0-9]+)", stripped)
            if match:
                return {
                    "source": match.group(1),
                    "device_name": match.group(2),
                    "online": True,
                    "raw_hex": stripped,
                }
        if len(stripped) >= 8 and all(ch in "0123456789abcdefABCDEF" for ch in stripped):
            parsed_frame = _parse_device_frame(stripped)
            if parsed_frame is not None:
                return parsed_frame
            return {"device_name": "Lumentree", "raw_hex": stripped}
        try:
            as_json = json.loads(stripped)
            return parse_realtime_payload(as_json)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring non-JSON MQTT payload: %s", stripped)
            return None
    return None
