from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEVICE_SN,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_POLLING,
    CONF_PORT,
    CONF_TOPIC,
    CONF_USERNAME,
    DEFAULT_POLLING,
    DEFAULT_PORT,
    DEFAULT_TOPIC,
    DOMAIN,
)


class LumentreeLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input.get(CONF_HOST, "")).strip()
            device_sn = str(user_input.get(CONF_DEVICE_SN, "")).strip()

            if not host:
                errors["base"] = "host_required"
            elif not device_sn:
                errors["base"] = "device_sn_required"
            else:
                await self.async_set_unique_id(f"{host}:{user_input[CONF_PORT]}:{device_sn}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=device_sn or host,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                        CONF_DEVICE_SN: device_sn,
                        CONF_POLLING: int(user_input.get(CONF_POLLING, DEFAULT_POLLING)),
                        CONF_TOPIC: DEFAULT_TOPIC,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=""): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Required(CONF_DEVICE_SN, default=""): str,
                vol.Optional(CONF_POLLING, default=DEFAULT_POLLING): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Support import from YAML or manual setup."""
        return await self.async_step_user(import_data)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the configuration entry data and return a normalized dict."""
    return {
        CONF_HOST: str(data[CONF_HOST]).strip(),
        CONF_PORT: int(data.get(CONF_PORT, DEFAULT_PORT)),
        CONF_USERNAME: data.get(CONF_USERNAME, ""),
        CONF_PASSWORD: data.get(CONF_PASSWORD, ""),
        CONF_DEVICE_SN: str(data.get(CONF_DEVICE_SN, "")).strip(),
        CONF_POLLING: int(data.get(CONF_POLLING, DEFAULT_POLLING)),
        CONF_TOPIC: data.get(CONF_TOPIC, DEFAULT_TOPIC),
    }
