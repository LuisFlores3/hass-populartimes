"""Popular Times integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Popular Times from a config entry."""
	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	# Listen for options/data updates to propagate to entities
	entry.async_on_unload(entry.add_update_listener(_async_update_listener))
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Handle config entry updates by reloading the entry.

	For this simple integration, reload is fine. If we want hot updates without
	reload, we can forward events to the platform later.
	"""
	await hass.config_entries.async_reload(entry.entry_id)
