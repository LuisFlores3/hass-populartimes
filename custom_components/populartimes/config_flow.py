"""Config flow for Popular Times integration."""
from __future__ import annotations

from typing import Any
import hashlib

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_ADDRESS
from homeassistant.core import callback

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

        # If the YAML address starts with a venue name in parentheses, e.g. "(Li'l Devil's), 255 S Broadway...",
        # extract that as a nicer Name and clean the Address for storage.
        name, address = _extract_name_and_clean_address(name, address)

        uid = _addr_unique_id(address)
        await self.async_set_unique_id(uid)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_ADDRESS: address})


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        return text[1:-1].strip()
    return text


def _looks_like_slug(text: str) -> bool:
    t = text.strip()
    return t == t.lower() and any(ch == '_' for ch in t)


def _extract_name_and_clean_address(current_name: str, address: str) -> tuple[str, str]:
    """If address has leading (Name), prefer that as Name and strip it from Address.

    Returns (name, cleaned_address).
    """
    cur_name = (current_name or "").strip()
    addr = _strip_quotes(address or "")
    if addr.startswith("("):
        end = addr.find(")")
        if end > 0:
            extracted = addr[1:end].strip()
            rest = addr[end + 1 :].lstrip(", ").strip()
            if extracted:
                # Prefer extracted pretty name if current name looks like a slug (e.g., bar_lil_devils)
                final_name = extracted if (not cur_name or _looks_like_slug(cur_name)) else cur_name
                return final_name, rest or addr
    return cur_name or addr, addr


class PopularTimesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Popular Times (currently minimal)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        data = self.config_entry.data
        defaults = {
            CONF_NAME: data.get(CONF_NAME, "Popular Times"),
            CONF_ADDRESS: data.get(CONF_ADDRESS, ""),
        }

        if user_input is not None:
            # Persist options (sensor_slug) and update entry data/title for name/address
            updates = {**data, CONF_NAME: user_input[CONF_NAME], CONF_ADDRESS: user_input[CONF_ADDRESS]}
            await self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updates,
                title=user_input[CONF_NAME],
                options={},
            )
            return self.async_create_entry(title="Options", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
                vol.Required(CONF_ADDRESS, default=defaults[CONF_ADDRESS]): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
