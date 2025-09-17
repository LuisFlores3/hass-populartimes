"""Config flow for Popular Times integration."""
from __future__ import annotations

from typing import Any
import hashlib

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


def _addr_unique_id(address: str) -> str:
    digest = hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"addr_{digest}"


class PopularTimesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Popular Times."""

    VERSION = 1
    MINOR_VERSION = 0

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            name = user_input[CONF_NAME]
            address = user_input[CONF_ADDRESS]

            uid = _addr_unique_id(address)
            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_ADDRESS: address})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_ADDRESS): str,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PopularTimesOptionsFlowHandler(config_entry)

    async def async_step_import(self, user_input: dict[str, Any]) -> config_entries.ConfigFlowResult:
        """Handle import from YAML (sensor platform)."""
        name = user_input[CONF_NAME]
        address = user_input[CONF_ADDRESS]

        uid = _addr_unique_id(address)
        await self.async_set_unique_id(uid)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_ADDRESS: address})


class PopularTimesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Popular Times (currently minimal)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # No options for now; return empty options to keep the structure ready
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)
        return self.async_create_entry(title="Options", data={})
