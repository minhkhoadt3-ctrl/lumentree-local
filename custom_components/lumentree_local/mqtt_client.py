from __future__ import annotations

import asyncio
import logging
import threading
import time
from functools import partial
from typing import Any, Callable, Dict, Optional

try:  # pragma: no cover - Home Assistant runtime only
    import paho.mqtt.client as paho
    from paho.mqtt.client import MQTTMessage
except ModuleNotFoundError:  # pragma: no cover - local/unit-test environment
    class _PahoFallback:
        CONNACK_ACCEPTED = 0
        MQTT_ERR_SUCCESS = 0
        MQTTv311 = 4
        Client = object

    paho = _PahoFallback()
    MQTTMessage = Any

try:  # pragma: no cover - Home Assistant runtime only
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from homeassistant.helpers.event import async_call_later
except ModuleNotFoundError:  # pragma: no cover - local/unit-test environment
    ConfigEntry = Any
    HomeAssistant = Any

    def callback(func):
        return func

    def async_dispatcher_send(hass: Any, signal: str, payload: Any) -> None:
        return None

    def async_call_later(hass: Any, delay: float, action):
        return lambda: None

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_SN,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    KEY_LAST_RAW_MQTT,
    KEY_ONLINE_STATUS,
    MQTT_BROKER,
    MQTT_CLIENT_ID_FORMAT,
    MQTT_KEEPALIVE,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_PUB_TOPIC_FORMAT,
    MQTT_SUB_TOPIC_FORMAT,
    MQTT_USERNAME,
    REG_ADDR_CELL_COUNT,
    REG_ADDR_CELL_START,
    SIGNAL_UPDATE_FORMAT,
)
from .realtime_parser import generate_modbus_read_command, parse_mqtt_payload

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_ATTEMPTS = 10
CONNECT_TIMEOUT = 20
OFFLINE_TIMEOUT_SECONDS = DEFAULT_POLLING_INTERVAL * 2.5
NUM_MAIN_REGISTERS_TO_READ = 70


class LumentreeMqttClient:
    """Manages MQTT connection, messages, and online status with batch updates."""

    __slots__ = (
        "hass",
        "entry",
        "callback",
        "_device_sn",
        "_device_id",
        "_mqttc",
        "_client_id",
        "_signal_update",
        "_topic_sub",
        "_topic_pub",
        "_topic_subs",
        "_poll_task",
        "_poll_interval",
        "_connect_lock",
        "_reconnect_attempts",
        "_is_connected",
        "_stopping",
        "_stopping_lock",
        "_connected_event",
        "_online",
        "_offline_timer_unsub",
        "_offline_timer_gen",
        "_batch_timer",
        "_pending_updates",
    )

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_sn: str,
        device_id: str,
        callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._device_sn = device_sn
        self._device_id = device_id
        self.callback = callback
        self._mqttc: Optional[paho.Client] = None

        timestamp = int(time.time())
        try:
            self._client_id = MQTT_CLIENT_ID_FORMAT.format(
                device_id=self._device_id, timestamp=timestamp
            )
        except KeyError:
            self._client_id = f"ha-lumentree-{self._device_sn}-{timestamp}"

        self._signal_update = SIGNAL_UPDATE_FORMAT.format(device_sn=self._device_sn)
        self._topic_sub = MQTT_SUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._topic_pub = MQTT_PUB_TOPIC_FORMAT.format(device_sn=self._device_sn)
        self._topic_subs = tuple(dict.fromkeys([self._topic_sub, f"reportApp/{self._device_sn}"]))
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._poll_interval = DEFAULT_POLLING_INTERVAL

        self._connect_lock = asyncio.Lock()
        self._reconnect_attempts = 0
        self._is_connected = False
        self._stopping = False
        self._stopping_lock = threading.Lock()
        self._connected_event = asyncio.Event()
        self._online = False
        self._offline_timer_unsub: Optional[Callable] = None
        self._offline_timer_gen = 0
        self._batch_timer: Optional[asyncio.Task] = None
        self._pending_updates: Dict[str, Any] = {}

    @property
    def topic_sub(self) -> str:
        return self._topic_sub

    @property
    def topic_pub(self) -> str:
        return self._topic_pub

    @property
    def topic_subs(self) -> tuple[str, ...]:
        return self._topic_subs

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def subscribe(self, topic: str | list[str] | tuple[str, ...] | None = None) -> None:
        """Store the intended subscription topics and register them when connected."""
        if topic is not None:
            topics = [topic] if isinstance(topic, str) else list(topic)
            self._topic_subs = tuple(dict.fromkeys(topics))
            if self._topic_subs:
                self._topic_sub = self._topic_subs[0]
        if self._mqttc is not None and self._is_connected:
            try:
                for sub_topic in self._topic_subs:
                    self._mqttc.subscribe(sub_topic, 0)
            except Exception as exc:
                _LOGGER.warning("MQTT subscribe failed %s: %s", self._client_id, exc)

    def _cancel_offline_timer(self) -> None:
        if self._offline_timer_unsub:
            try:
                self._offline_timer_unsub()
            except Exception as exc:
                _LOGGER.warning("Error cancelling timer %s: %s", self._client_id, exc)
            self._offline_timer_unsub = None

    def _cancel_batch_timer(self) -> None:
        if self._batch_timer is not None:
            try:
                self._batch_timer.cancel()
            except Exception as exc:
                _LOGGER.warning("Error cancelling batch timer %s: %s", self._client_id, exc)
            self._batch_timer = None

    async def _start_batch_timer(self) -> None:
        if self._batch_timer is not None:
            self._batch_timer.cancel()
        self._batch_timer = asyncio.create_task(self._process_batch_updates())

    async def _process_batch_updates(self) -> None:
        try:
            await asyncio.sleep(0.1)
            if self._pending_updates:
                async_dispatcher_send(self.hass, self._signal_update, self._pending_updates.copy())
                self._pending_updates.clear()
        except asyncio.CancelledError:
            if self._pending_updates:
                async_dispatcher_send(self.hass, self._signal_update, self._pending_updates.copy())
                self._pending_updates.clear()
        except Exception as exc:
            _LOGGER.error("Error in batch update processing: %s", exc)
        finally:
            self._batch_timer = None

    def _queue_update(self, data: Dict[str, Any]) -> None:
        self._pending_updates.update(data)
        if self._batch_timer is None:
            self.hass.loop.call_soon_threadsafe(
                lambda: self.hass.async_create_task(self._start_batch_timer())
            )

    @callback
    def _set_offline(self, gen: int = -1, *args) -> None:
        if gen >= 0 and gen != self._offline_timer_gen:
            return
        _LOGGER.info("MQTT data timeout or disconnect %s. Setting offline.", self._client_id)
        self.hass.loop.call_soon_threadsafe(self._cancel_offline_timer)
        if self._online:
            self._online = False
            async_dispatcher_send(self.hass, self._signal_update, {KEY_ONLINE_STATUS: False})

    def _start_offline_timer(self) -> None:
        self.hass.loop.call_soon_threadsafe(self._cancel_offline_timer)
        self._offline_timer_gen += 1
        gen = self._offline_timer_gen
        self._offline_timer_unsub = async_call_later(
            self.hass, OFFLINE_TIMEOUT_SECONDS, lambda _now: self._set_offline(gen)
        )

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._is_connected:
                return

            self._stopping = False
            self._connected_event.clear()
            self._mqttc = paho.Client(client_id=self._client_id, protocol=paho.MQTTv311)
            self._mqttc.username_pw_set(
                username=self.entry.data.get(CONF_USERNAME, MQTT_USERNAME),
                password=self.entry.data.get(CONF_PASSWORD, MQTT_PASSWORD),
            )
            self._mqttc.on_connect = self._on_connect
            self._mqttc.on_disconnect = self._on_disconnect
            self._mqttc.on_message = self._on_message

            host = self.entry.data.get(CONF_HOST, MQTT_BROKER)
            port = int(self.entry.data.get(CONF_PORT, MQTT_PORT))
            _LOGGER.info("MQTT connecting: %s:%s (Client: %s) for SN: %s", host, port, self._client_id, self._device_sn)

            try:
                await self.hass.async_add_executor_job(self._mqttc.connect, host, port, MQTT_KEEPALIVE)
                self._mqttc.loop_start()
                try:
                    await asyncio.wait_for(self._connected_event.wait(), timeout=CONNECT_TIMEOUT)
                    if not self._is_connected:
                        raise ConnectionRefusedError("MQTT connection refused")
                except asyncio.TimeoutError:
                    _LOGGER.error("MQTT connection timeout %s", self._client_id)
                    await self.disconnect()
                    raise ConnectionRefusedError("MQTT connection timeout")
            except Exception as exc:
                _LOGGER.error("Failed MQTT connect %s: %s", self._client_id, exc)
                if self._mqttc:
                    try:
                        self._mqttc.loop_stop()
                    except Exception:
                        pass
                self._mqttc = None
                self._is_connected = False
                self._connected_event.set()
                raise ConnectionRefusedError(f"MQTT setup error: {exc}") from exc

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc == paho.CONNACK_ACCEPTED:
            _LOGGER.info("MQTT connected (rc=%s) %s. Subscribing to: %s", rc, self._client_id, self._topic_subs)
            self._reconnect_attempts = 0
            try:
                for sub_topic in self._topic_subs:
                    result, mid = client.subscribe(sub_topic, 0)
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("Subscribe %s %s (mid=%s)", "OK" if result == 0 else "Failed", sub_topic, mid)
                self._is_connected = True
                self.hass.loop.call_soon_threadsafe(self.start_polling, self._poll_interval)
            except Exception as exc:
                _LOGGER.error("MQTT subscribe failed %s: %s", self._client_id, exc)
                self._is_connected = False
                self.hass.loop.call_soon_threadsafe(self._connected_event.set)
                self.hass.loop.call_soon_threadsafe(self._set_offline)
                self.hass.loop.call_soon_threadsafe(self._safe_schedule_reconnect)
                return
            self.hass.loop.call_soon_threadsafe(self._connected_event.set)
        else:
            _LOGGER.error("MQTT connection refused %s (rc=%s)", self._client_id, rc)
            self._is_connected = False
            self.hass.loop.call_soon_threadsafe(self._connected_event.set)
            self.hass.loop.call_soon_threadsafe(self._set_offline)
            self.hass.loop.call_soon_threadsafe(self._safe_schedule_reconnect)

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        self._is_connected = False
        self.hass.loop.call_soon_threadsafe(self._cancel_offline_timer)
        self.hass.loop.call_soon_threadsafe(self._set_offline)

        if rc == 0 and self._stopping:
            _LOGGER.info("MQTT clean disconnect %s (rc=%s)", self._client_id, rc)
            return

        if rc == 0:
            _LOGGER.info("MQTT connection closed cleanly %s (rc=%s)", self._client_id, rc)
            return

        _LOGGER.warning("MQTT unexpected disconnect %s (rc=%s)", self._client_id, rc)
        self.hass.loop.call_soon_threadsafe(self._safe_schedule_reconnect)

    @callback
    def _safe_schedule_reconnect(self) -> None:
        if not self._stopping:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        self._reconnect_attempts += 1
        delay = min(RECONNECT_DELAY_SECONDS * (2 ** (self._reconnect_attempts - 1)), 60)
        _LOGGER.info("Scheduling MQTT reconnect %s/%s for %s in %ss", self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS, self._client_id, delay)
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._async_reconnect(delay))
        )

    async def _async_reconnect(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if self._stopping:
            return
        if not self.is_connected and self._mqttc:
            try:
                await self.hass.async_add_executor_job(self._mqttc.reconnect)
            except Exception as exc:
                _LOGGER.warning("MQTT soft reconnect failed %s: %s", self._client_id, exc)

    async def _hard_reconnect(self) -> None:
        _LOGGER.info("MQTT hard reconnect: creating fresh connection %s", self._client_id)
        old_mqttc = self._mqttc
        self._mqttc = None
        self._cancel_batch_timer()
        self._pending_updates.clear()
        if old_mqttc:
            try:
                old_mqttc.loop_stop()
            except Exception:
                pass
            try:
                old_mqttc.disconnect()
            except Exception:
                pass
        self._is_connected = False
        self._connected_event.clear()
        self._stopping = False
        try:
            await self.connect()
        except Exception as exc:
            _LOGGER.error("MQTT hard reconnect failed %s: %s", self._client_id, exc)
            self._stopping = False
            self._reconnect_attempts = MAX_RECONNECT_ATTEMPTS
            self._schedule_reconnect()

    def start_polling(self, interval: float | None = None) -> None:
        """Start a periodic read request loop to trigger reportApp responses."""
        if interval is not None:
            self._poll_interval = interval
        if self._poll_task is not None and not self._poll_task.done():
            _LOGGER.debug("MQTT polling already running for %s interval=%ss", self._client_id, self._poll_interval)
            return
        _LOGGER.info(
            "Starting MQTT poll loop for %s: topic=%s interval=%ss",
            self._client_id,
            self._topic_pub,
            self._poll_interval,
        )
        self._poll_task = self.hass.async_create_task(self._poll_loop())

    async def stop_polling(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        poll_count = 0
        while not self._stopping:
            if self._is_connected and self._mqttc:
                poll_count += 1
                _LOGGER.info(
                    "MQTT poll tick #%s for %s: sending read request to %s",
                    poll_count,
                    self._client_id,
                    self._topic_pub,
                )
                await self.async_request_data()
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    def _on_message(self, client, userdata, msg: MQTTMessage) -> None:
        topic = msg.topic
        try:
            payload_bytes = msg.payload
            payload_hex = "".join(f"{b:02x}" for b in payload_bytes) if payload_bytes else ""
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("MQTT message received %s: topic='%s', payload='%s...' (len: %s)", self._client_id, topic, payload_hex[:60], len(payload_bytes))

            if topic in self._topic_subs or topic.endswith(f"/{self._device_sn}"):
                parsed_data = parse_mqtt_payload(payload_hex)
                if parsed_data:
                    _LOGGER.info(
                        "MQTT response parsed for %s on topic=%s keys=%s",
                        self._client_id,
                        topic,
                        sorted(parsed_data.keys())[:20],
                    )
                    if not self._online:
                        self._online = True
                        parsed_data[KEY_ONLINE_STATUS] = True
                    self.hass.loop.call_soon_threadsafe(self._start_offline_timer)
                    parsed_data[KEY_LAST_RAW_MQTT] = payload_hex
                    parsed_data["mqtt_topic"] = topic
                    if callable(self.callback):
                        self.hass.loop.call_soon_threadsafe(self.callback, parsed_data)
                    self.hass.loop.call_soon_threadsafe(self._queue_update, parsed_data)
                else:
                    _LOGGER.warning(
                        "MQTT payload received but not parsed for %s topic=%s len=%s payload=%s",
                        self._client_id,
                        topic,
                        len(payload_bytes),
                        payload_hex[:120],
                    )
            else:
                _LOGGER.warning("Unexpected topic %s: %s", self._client_id, topic)
        except Exception as exc:
            _LOGGER.exception("Error processing MQTT message %s %s", topic, self._client_id)

    async def _publish_command(self, command_hex: str) -> bool:
        if not self.is_connected or not self._mqttc:
            _LOGGER.error("MQTT not connected %s, cannot publish", self._client_id)
            return False
        try:
            payload_bytes = bytes.fromhex(command_hex)
            _LOGGER.debug(
                "MQTT publish request %s -> topic=%s payload=%s len=%s",
                self._client_id,
                self._topic_pub,
                command_hex,
                len(payload_bytes),
            )
            msg_info = await self.hass.async_add_executor_job(
                partial(self._mqttc.publish, self._topic_pub, payload=payload_bytes, qos=0)
            )
            if msg_info is None or msg_info.rc != paho.MQTT_ERR_SUCCESS:
                _LOGGER.error("MQTT publish failed %s RC: %s", self._client_id, getattr(msg_info, "rc", "Executor Error"))
                return False
            _LOGGER.debug(
                "MQTT publish accepted %s -> topic=%s rc=%s payload=%s",
                self._client_id,
                self._topic_pub,
                getattr(msg_info, "rc", "unknown"),
                command_hex,
            )
            return True
        except ValueError as exc:
            _LOGGER.error("Invalid hex payload %s: %s", self._client_id, exc)
            return False
        except Exception as exc:
            _LOGGER.error("Failed MQTT publish %s: %s", self._client_id, exc)
            return False

    async def async_request_data(self) -> None:
        slave_id = 1
        func_code = 3
        start_address = 0
        num_registers = NUM_MAIN_REGISTERS_TO_READ
        command_hex = generate_modbus_read_command(slave_id, func_code, start_address, num_registers)
        if command_hex:
            _LOGGER.info(
                "Requesting inverter data %s: topic=%s start=%s count=%s frame=%s",
                self._client_id,
                self._topic_pub,
                start_address,
                num_registers,
                command_hex,
            )
            await self._publish_command(command_hex)
        else:
            _LOGGER.error("Failed to generate Modbus read (0-%s) %s", num_registers - 1, self._client_id)

    async def async_request_battery_cells(self) -> None:
        slave_id = 1
        func_code = 3
        start = REG_ADDR_CELL_START
        count = REG_ADDR_CELL_COUNT
        command_hex = generate_modbus_read_command(slave_id, func_code, start, count)
        if command_hex:
            await self._publish_command(command_hex)
        else:
            _LOGGER.error("Failed to generate Modbus read (%s-%s) %s", start, start + count - 1, self._client_id)

    async def disconnect(self) -> None:
        _LOGGER.info("Disconnecting MQTT %s", self._client_id)
        self._stopping = True
        self._reconnect_attempts = MAX_RECONNECT_ATTEMPTS
        self._connected_event.set()
        self.hass.loop.call_soon_threadsafe(self._cancel_offline_timer)
        self._cancel_batch_timer()
        await self.stop_polling()
        self.hass.loop.call_soon_threadsafe(self._set_offline)

        mqttc_to_disconnect = None
        async with self._connect_lock:
            if self._mqttc:
                mqttc_to_disconnect = self._mqttc
                self._mqttc = None
            self._is_connected = False

        if mqttc_to_disconnect:
            try:
                try:
                    await self.hass.async_add_executor_job(mqttc_to_disconnect.unsubscribe, self._topic_sub)
                except Exception as unsub_exc:
                    _LOGGER.warning("Error unsubscribing from %s %s: %s", self._topic_sub, self._client_id, unsub_exc)
                await self.hass.async_add_executor_job(mqttc_to_disconnect.loop_stop)
                await self.hass.async_add_executor_job(mqttc_to_disconnect.disconnect)
                _LOGGER.info("MQTT client disconnected %s", self._client_id)
            except Exception as exc:
                _LOGGER.warning("Error during MQTT disconnect %s: %s", self._client_id, exc)
