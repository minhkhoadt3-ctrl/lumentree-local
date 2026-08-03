from __future__ import annotations

import json
import re
from typing import Any, Mapping, Optional
"""Real-time MQTT payload parser for Lumentree integration.

This module handles parsing of real-time MQTT data from Lumentree inverters.
All parsing functions are optimized for performance with cached struct formats.
"""

from typing import Optional, Dict, Any, Tuple
import logging
import struct
import math
import time

from .const import (
    REG_ADDR,
    KEY_ONLINE_STATUS,
    KEY_BATTERY_POWER,
    KEY_BATTERY_SOC,
    KEY_GRID_POWER,
    KEY_LOAD_POWER,
    KEY_BATTERY_VOLTAGE,
    KEY_BATTERY_CURRENT,
    KEY_AC_OUT_VOLTAGE,
    KEY_AC_OUT_FREQ,
    KEY_AC_OUT_POWER,
    KEY_AC_OUT_CURRENT,
    KEY_AC_OUT_VA,
    KEY_DEVICE_TEMP,
    KEY_MPPT_TEMP,
    KEY_PV1_VOLTAGE,
    KEY_PV1_POWER,
    KEY_PV2_POWER,
    KEY_AC_IN_POWER,
    KEY_AC_IN_CURRENT,
    KEY_FW_VERSION,
    KEY_CTRL_VERSION,
    KEY_PV1_CURRENT,
    KEY_MQTT_DEVICE_SN,
    KEY_DAILY_PV_KWH,
    KEY_DAILY_CHARGE_KWH,
    KEY_DAILY_DISCHARGE_KWH,
    KEY_DAILY_LOAD_KWH,
    KEY_DAILY_ESSENTIAL_KWH,
    KEY_DAILY_TOTAL_LOAD_KWH,
    KEY_MONTHLY_GRID_IN_KWH,
    KEY_MONTHLY_LOAD_KWH,
    KEY_MONTHLY_ESSENTIAL_KWH,
)

import crcmod.predefined

crc16_modbus_func = crcmod.predefined.mkCrcFun("modbus")

_LOGGER = logging.getLogger(__name__)

_last_regs_log = {}
# Cached struct format strings for performance (40-50% faster parsing)
_STRUCT_FORMATS: Dict[str, struct.Struct] = {
    "signed_2": struct.Struct(">h"),  # Signed 16-bit big-endian
    "unsigned_2": struct.Struct(">H"),  # Unsigned 16-bit big-endian
    "signed_4": struct.Struct(">i"),  # Signed 32-bit big-endian
    "unsigned_4": struct.Struct(">I"),  # Unsigned 32-bit big-endian
}


def calculate_crc16_modbus(pb: bytes) -> Optional[int]:
    """Calculate Modbus CRC16.

    Args:
        pb: Payload bytes

    Returns:
        CRC16 value or None if calculation fails
    """
    if crc16_modbus_func:
        try:
            return crc16_modbus_func(pb)
        except Exception:
            return None
    return None


def verify_crc(ph: str) -> Tuple[bool, Optional[str]]:
    """Verify CRC of payload hex string.

    Args:
        ph: Payload hex string

    Returns:
        Tuple of (is_valid, error_message)
    """
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

        if not ok:
            _LOGGER.warning(f"CRC mismatch! Received: {rc}, Calculated: {cch}")
        else:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("CRC check successful")

        return ok, None if ok else f"Mismatch {rc} vs {cch}"
    except Exception:
        return False, "Verify error"


def generate_modbus_read_command(sid: int, fc: int, addr: int, num: int) -> Optional[str]:
    """Generate a Modbus read command hex string with CRC.

    Args:
        sid: Slave ID
        fc: Function code
        addr: Start address
        num: Number of registers

    Returns:
        Command hex string or None if generation fails
    """
    if not crc16_modbus_func:
        _LOGGER.error("Cannot generate command: crcmod library missing")
        return None

    try:
        pdu = bytearray([fc]) + addr.to_bytes(2, "big") + num.to_bytes(2, "big")
        adu = bytearray([sid]) + pdu
        crc = calculate_crc16_modbus(bytes(adu))

        if crc is None:
            _LOGGER.error("CRC calculation failed")
            return None

        full = adu + crc.to_bytes(2, "little")
        command_hex = full.hex()

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Generated Modbus command: %s", command_hex)

        return command_hex
    except Exception as exc:
        _LOGGER.exception(f"Error generating Modbus command: {exc}")
        return None


def _read_register(
    db: bytes, ra: int, signed: bool, factor: float = 1.0, byte_count: int = 2
) -> Optional[float]:
    """Read register value with cached struct formats for performance.

    Args:
        db: Data bytes
        ra: Register address (offset)
        signed: Whether value is signed
        factor: Multiplication factor
        byte_count: Number of bytes (2 or 4)

    Returns:
        Register value or None if reading fails
    """
    offset_bytes = ra * 2

    if offset_bytes + byte_count > len(db):
        return None

    try:
        raw_bytes = db[offset_bytes : offset_bytes + byte_count]

        # Use cached struct formats for performance
        if byte_count == 2:
            fmt = _STRUCT_FORMATS["signed_2"] if signed else _STRUCT_FORMATS["unsigned_2"]
        elif byte_count == 4:
            fmt = _STRUCT_FORMATS["signed_4"] if signed else _STRUCT_FORMATS["unsigned_4"]
        else:
            _LOGGER.warning(f"Unsupported byte_count {byte_count}")
            return None

        raw_val = fmt.unpack(raw_bytes)[0]
        result = round(raw_val * factor, 3)

        if not math.isfinite(result):
            _LOGGER.warning(f"Invalid float read from register {ra}")
            return None

        return result
    except struct.error as exc:
        _LOGGER.error(f"Struct error reading register {ra}: {exc}")
        return None
    except Exception as exc:
        _LOGGER.exception(f"Unexpected error reading register {ra}: {exc}")
        return None


def _make_reader(db: bytes, addr_map: dict):
    """Create a fast register reader bound to a specific data buffer and address map.

    Returns a callable that avoids recreating closures on each parse_mqtt_payload call.
    """

    def read_reg(key: str, signed: bool, factor: float = 1.0, byte_count: int = 2):
        r = addr_map.get(key)
        if r is not None:
            return _read_register(db, r, signed, factor, byte_count)
        return None

    return read_reg


def _read_string(db: bytes, sa: int, nr: int) -> Optional[str]:
    """Read ASCII string from registers.

    Args:
        db: Data bytes
        sa: Start address
        nr: Number of registers

    Returns:
        Decoded string or None if reading fails
    """
    offset = sa * 2
    num_bytes = nr * 2

    if offset + num_bytes > len(db):
        return None

    try:
        raw_bytes = db[offset : offset + num_bytes]
        decoded_string = (
            raw_bytes.decode("ascii", "ignore").replace("\x00", "").strip()
        )
        return decoded_string if decoded_string else None
    except Exception:
        return None



def parse_mqtt_payload(ph: str) -> Optional[Dict[str, Any]]:
    """Parse MQTT payload hex string.

    This is the main entry point for parsing real-time MQTT data from Lumentree inverters.
    Handles both main data (95 registers) and battery cell data.

    Args:
        ph: Payload hex string

    Returns:
        Parsed data dictionary or None if parsing fails

    Raises:
        None - All exceptions are caught and logged, returns None on error
    """
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug("Parsing payload: %s...", ph[:100])

    parsed_data: Dict[str, Any] = {}
    db: Optional[bytes] = None
    
    resp_hex: Optional[str] = None
    sep = "2b2b2b2b"

    # Extract response hex from payload
    if sep in ph:
        parts = ph.split(sep)
        resp_hex = (
            parts[1]
            if len(parts) == 2 and (parts[1].startswith("0103") or parts[1].startswith("0104"))
            else None
        )
    elif ph.startswith("0103") or ph.startswith("0104"):
        resp_hex = ph

    if not resp_hex or len(resp_hex) < 12:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Invalid payload format or too short")
        return None

    try:
        crc_ok, crc_err = verify_crc(resp_hex)
        if not crc_ok:
            _LOGGER.warning("CRC verification failed: %s", crc_err)
            return None
        bc = int(resp_hex[4:6], 16)
        dh = resp_hex[6:-4]
        db = bytes.fromhex(dh)
        if len(db) != bc:
            _LOGGER.debug(
                "Length mismatch: payload=%s bytes, reported_bc=%s",
                len(db),
                bc,
            )
        if len(db) == 0 and bc > 0:
            _LOGGER.error("No data bytes")
            return None

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Parsing %s bytes", len(db))

        expected_main_bytes = 70  * 2  # 151 rut gon ve 68 registers (0-150), 302 bytes
        expected_main_bytes_legacy = 95 * 2  # Legacy 95-register format
        expected_main_bytes_extended = expected_main_bytes_legacy + 12  # Legacy + metadata

        # Determine data type
        # Determine data type based on actual payload length
        # Some newer firmware reports unexpected byte-count values
        # while still delivering valid payloads.

        if len(db) == expected_main_bytes:
            
            _LOGGER.debug(
                "Main data (151 regs, %s bytes, reported bc=%s)",
                len(db),
                bc,
            )

        elif len(db) == expected_main_bytes_legacy:
            
            _LOGGER.debug(
                "Main data (legacy 95 regs, %s bytes, reported bc=%s)",
                len(db),
                bc,
            )

        elif len(db) == expected_main_bytes_extended:
            
            _LOGGER.debug(
                "Main data (legacy + metadata, %s bytes, reported bc=%s)",
                len(db),
                bc,
            )
            db = db[:expected_main_bytes_legacy]
        elif len(db) == 198 and bc == 198:
            # 198 bytes = 99 registers, likely main data with partial metadata (missing 4 bytes)
            # Try parsing as legacy main data (190 bytes) - skip last 8 bytes
            
            _LOGGER.debug("Main data (198 bytes, likely 99 regs - treating as 95 regs)")
            db = db[:expected_main_bytes_legacy]
        elif len(db) == 2:
            # 2 bytes = Modbus exception response or error
            _LOGGER.debug(
                f"Modbus exception/error response (2 bytes): {resp_hex[:20]}... "
                f"(function_code={resp_hex[2:4] if len(resp_hex) >= 4 else 'N/A'})"
            )
            return None
        elif len(db) <= 20:
            # Very short responses - likely error or control messages
            _LOGGER.debug(
                f"Short response ({len(db)} bytes) - likely error/control: "
                f"{resp_hex[:min(50, len(resp_hex))]}..."
            )
            return None
        else:
            # Unknown length - log with more context but try to parse if it's close to expected
            _LOGGER.debug(
                "Unrecognized length (%s/%s). Expected: %s or %s for main. "
                "Payload preview: %s...",
                len(db), bc, expected_main_bytes, expected_main_bytes_legacy,
                resp_hex[:min(60, len(resp_hex))],
            )
            # If length is close to any expected main format, try parsing
            for expected_len in (expected_main_bytes, expected_main_bytes_legacy):
                if abs(len(db) - expected_len) <= 20 and len(db) >= expected_len - 10:
                    _LOGGER.debug("Attempting to parse %s bytes as main data", len(db))
                    
                    if len(db) > expected_len:
                        db = db[:expected_len]
                    else:
                        db = db + b'\x00' * (expected_len - len(db))
                    break
            else:
                return None

    
        # Parse main registers with optimized read helper (module-level function)
        rr = _make_reader(db, REG_ADDR)

        # Battery voltage
        bat_volt = rr("BATTERY_VOLTAGE", False, 0.01)
        if bat_volt is not None:
            parsed_data[KEY_BATTERY_VOLTAGE] = bat_volt

        # Battery current (inverted to match card convention)
        # Positive = Charging, Negative = Discharging (matches battery power)
        bat_curr = rr("BATTERY_CURRENT", True, 0.01)
        if bat_curr is not None:
            parsed_data[KEY_BATTERY_CURRENT] = -bat_curr  # Invert sign for card compatibility

        # AC output voltage
        ac_out_v = rr("AC_OUT_VOLTAGE", False, 0.1)
        if ac_out_v is not None:
            parsed_data[KEY_AC_OUT_VOLTAGE] = ac_out_v

        # AC output current    
        ac_out_curr = rr("AC_OUT_CURRENT", True, 0.01)
        if ac_out_curr is not None:
            parsed_data[KEY_AC_OUT_CURRENT] = ac_out_curr

        # Grid voltage (also AC input voltage)    
        ac_in_curr = rr("AC_IN_CURRENT", True, 0.01)
        if ac_in_curr is not None:
            parsed_data[KEY_AC_IN_CURRENT] = -ac_in_curr  # Invert sign for card compatibility

        # AC output frequency
        ac_out_f = rr("AC_OUT_FREQ", False, 0.01)
        if ac_out_f is not None:
            parsed_data[KEY_AC_OUT_FREQ] = ac_out_f

        # Device temperature
        temp_raw = rr("DEVICE_TEMP", True)
        if temp_raw is not None:
            temp_c = round((temp_raw - 1000) / 10, 1)
            parsed_data[KEY_DEVICE_TEMP] = temp_c if -40 < temp_c < 150 else None
            
        # MPPT temperature
        temp1_raw = rr("MPPT_TEMP", True)
        if temp1_raw is not None:
            temp1_c = round((temp1_raw - 1000) / 10, 1)
            parsed_data[KEY_MPPT_TEMP] = temp1_c if -40 < temp1_c < 150 else None    

        # PV voltages
        pv1_v = rr("PV1_VOLTAGE", False)
        if pv1_v is not None:
            parsed_data[KEY_PV1_VOLTAGE] = pv1_v
        
        # Grid power
        grid_p = rr("GRID_POWER", True)
        if grid_p is not None:
            parsed_data[KEY_GRID_POWER] = grid_p

        # Load power
        load_p = rr("LOAD_POWER", False)
        if load_p is not None:
            parsed_data[KEY_LOAD_POWER] = load_p

        # AC output power
        ac_out_p = rr("AC_OUT_POWER", False)
        if ac_out_p is not None:
            parsed_data[KEY_AC_OUT_POWER] = ac_out_p

        # Battery power and status (inverted to match card convention)
        # Positive = Charging, Negative = Discharging (for card compatibility)
        bp_signed = rr("BATTERY_POWER", True)
        if bp_signed is not None:
            parsed_data[KEY_BATTERY_POWER] = -bp_signed  # Invert sign for card compatibility
        else:
            parsed_data[KEY_BATTERY_POWER] = None
        #----------------------------------------------------------------------------------------------------------    
        # Monthly grid import
        monthly_grid = rr("MONTHLY_GRID_IN_KWH", True)
        if monthly_grid is not None:
            parsed_data[KEY_MONTHLY_GRID_IN_KWH] = -monthly_grid

        # Monthly load
        monthly_load = rr("MONTHLY_LOAD_KWH", False)
        if monthly_load is not None:
            parsed_data[KEY_MONTHLY_LOAD_KWH] = monthly_load

        # Monthly essential load
        monthly_essential = rr("MONTHLY_ESSENTIAL_KWH", False)
        if monthly_essential is not None:
            parsed_data[KEY_MONTHLY_ESSENTIAL_KWH] = -monthly_essential
            
        # Daily PV energy
        daily_pv = rr("DAILY_PV_KWH", False, 0.1)
        if daily_pv is not None:
            parsed_data[KEY_DAILY_PV_KWH] = daily_pv

        # Daily charge energy
        daily_charge = rr("DAILY_CHARGE_KWH", False, 0.1)
        if daily_charge is not None:
            parsed_data[KEY_DAILY_CHARGE_KWH] = daily_charge

        # Daily discharge energy
        daily_discharge = rr("DAILY_DISCHARGE_KWH", False, 0.1)
        if daily_discharge is not None:
            parsed_data[KEY_DAILY_DISCHARGE_KWH] = daily_discharge

        # Daily load energy
        daily_load = rr("DAILY_LOAD_KWH", False, 0.1)
        if daily_load is not None:
            parsed_data[KEY_DAILY_LOAD_KWH] = daily_load

        # Daily essential load energy
        daily_essential = rr("DAILY_ESSENTIAL_KWH", False, 0.1)
        if daily_essential is not None:
            parsed_data[KEY_DAILY_ESSENTIAL_KWH] = daily_essential

        # Daily total load energy
        if daily_load is not None and daily_essential is not None:
            parsed_data[KEY_DAILY_TOTAL_LOAD_KWH] = daily_load + daily_essential
        
        ac_out_va=rr("AC_OUT_VA",False)
        if ac_out_va is not None: 
            parsed_data[KEY_AC_OUT_VA]=ac_out_va
            
        # Grid status------------------------------------------------------------------------

        # PV power
        pv1 = rr("PV1_POWER", False)
        if pv1 is not None:
            parsed_data[KEY_PV1_POWER] = pv1
        
        # PV power
        pv2 = rr("PV2_POWER", False)
        if pv2 is not None:
            parsed_data[KEY_PV2_POWER] = pv2
        # PV1 current (A = W / V)
        if pv1 is not None and pv1_v and pv1_v > 5:
            parsed_data[KEY_PV1_CURRENT] = round(pv1 / pv1_v, 2)
        else:
            parsed_data[KEY_PV1_CURRENT] = 0
            
        # Battery SOC
        soc = rr("BATTERY_SOC", False)
        soc_value = max(0, min(100, int(soc))) if soc is not None else None
        if soc_value is not None:
            parsed_data[KEY_BATTERY_SOC] = soc_value
            
        # Device SN
        device_sn = _read_string(db, REG_ADDR["DEVICE_MODEL_START"], 5)
        if device_sn is not None:
            parsed_data[KEY_MQTT_DEVICE_SN] = device_sn

        # Firmware version (register 2, within range)
        fw_ver = rr("FIRMWARE_VERSION", False)
        if fw_ver is not None:
            parsed_data[KEY_FW_VERSION] = f"v{int(fw_ver)}"

        # Controller version (register 8, within range)
        ctrl_ver = rr("CONTROLLER_VERSION", False)
        if ctrl_ver is not None:
            parsed_data[KEY_CTRL_VERSION] = f"v{int(ctrl_ver)}"
                
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Parsed main data: %s", parsed_data)

    except Exception as exc:
        _LOGGER.exception(f"Parse error: {exc}")
        return None

    if parsed_data:
        data_type = "Main"
        global _last_regs_log

        now = time.monotonic()
        device_id = parsed_data.get(KEY_MQTT_DEVICE_SN, "unknown")
        device_id = device_id[-3:]
        last = _last_regs_log.get(device_id, 0)
        if now - last >= 600:  # 5 phút
            _last_regs_log[device_id] = now

            #regs = [51, 34, 64]
            #regs = [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 52, 55, 56, 58, 64, 65, 66]
            regs = [14, 19, 23, 26, 27, 28, 29, 30, 31, 32, 34, 35, 36, 38, 39, 40, 43, 44, 45, 46, 48, 49, 51, 52, 55, 56, 57, 58, 60, 64, 65, 66]
            _LOGGER.info(
                "[%s]: %s",
                device_id,
                " | ".join(
                    f"R{i}={int.from_bytes(db[i*2:i*2+2], 'big', signed=True)}"
                    for i in regs
                ),
            )
           
        return parsed_data
    else:
        _LOGGER.warning(f"No data parsed from: {resp_hex[:60] if resp_hex else 'N/A'}...")
        return None
