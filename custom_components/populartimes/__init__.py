"""Popular Times integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN
from homeassistant.const import CONF_NAME

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Popular Times from a config entry."""
	# Ensure domain data storage
	domain_data = hass.data.setdefault(DOMAIN, {})

	# Keep the entry title in sync with the configured Name (options preferred)
	desired_title = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, entry.title))
	if desired_title and entry.title != desired_title:
		# Avoid triggering an extra reload cycle when we update the title
		domain_data["skip_next_reload"] = True
		hass.config_entries.async_update_entry(entry, title=desired_title)

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	# Listen for options/data updates to propagate to entities and keep title synced
	entry.async_on_unload(entry.add_update_listener(_async_update_listener))
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Handle config entry updates: sync title and then reload when needed."""
	domain_data = hass.data.setdefault(DOMAIN, {})

	# If the last update was just a title sync, skip this reload once
	if domain_data.get("skip_next_reload"):
		domain_data["skip_next_reload"] = False
		return

	# Keep the entry title aligned with Name
	from homeassistant.const import CONF_NAME as _CONF_NAME  # local import to avoid editor nags
	desired_title = entry.options.get(_CONF_NAME, entry.data.get(_CONF_NAME, entry.title))
	if desired_title and entry.title != desired_title:
		# Update title first, then skip the subsequent reload from this update
		domain_data["skip_next_reload"] = True
		hass.config_entries.async_update_entry(entry, title=desired_title)
		return

	await hass.config_entries.async_reload(entry.entry_id)
