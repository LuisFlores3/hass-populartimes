"""Popular Times integration."""

from __future__ import annotations

import logging
from datetime import timedelta, datetime
import asyncio
import random

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from homeassistant.const import CONF_NAME, CONF_ADDRESS
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Popular Times from a config entry."""
	# Ensure domain data storage
	domain_data = hass.data.setdefault(DOMAIN, {})

	# Build a coordinator per entry to centralize polling and retries
	async def _async_update_data() -> dict:
		# Read current values (options preferred)
		name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, ""))
		address = entry.options.get(CONF_ADDRESS, entry.data.get(CONF_ADDRESS, ""))

		# Build query using both name and address (avoid duplicating name if already present)
		name_s = (name or "").strip()
		addr_s = (address or "").strip()
		if name_s:
			n = name_s.lower()
			a = addr_s.lower()
			if a.startswith(n) or a.startswith(f"{n},") or a.startswith(f"{n} "):
				query = addr_s
			else:
				query = f"{name_s}, {addr_s}" if addr_s else name_s
		else:
			query = addr_s

		# Import lazily to avoid editor warnings and ensure module load at runtime
		import livepopulartimes  # type: ignore

		# Retry with exponential backoff and jitter for transient errors
		max_attempts = 4
		delay = 1.0  # seconds
		max_delay = 8.0
		last_exc: Exception | None = None
		result = None
		for attempt in range(1, max_attempts + 1):
			try:
				result = await hass.async_add_executor_job(
					livepopulartimes.get_populartimes_by_address, query
				)
				# Treat empty result as retryable once or twice; Google can be flaky
				if result:
					break
				raise UpdateFailed(f"No data returned for '{address}'")
			except Timeout as req_err:
				last_exc = req_err
				retryable = True
			except ConnectError as req_err:
				last_exc = req_err
				retryable = True
			except HTTPError as req_err:
				last_exc = req_err
				status = getattr(getattr(req_err, "response", None), "status_code", None)
				retryable = status in (429, 502, 503, 504) or (status is not None and status >= 500)
				if not retryable:
					raise UpdateFailed(
						f"HTTP error fetching '{address}' (status {status}): {req_err}"
					) from req_err
			except UpdateFailed as ex:  # raised above for empty result
				last_exc = ex
				retryable = attempt < max_attempts  # try a couple of times
			except Exception as ex:  # noqa: BLE001
				# Non-network unexpected errors are not retryable
				raise UpdateFailed(f"Unexpected error fetching '{address}': {ex}") from ex

			if attempt < max_attempts and retryable:
				# Exponential backoff with jitter
				sleep_for = min(delay, max_delay)
				jitter = random.uniform(0, 0.4 * sleep_for)
				total_sleep = sleep_for + jitter
				_LOGGER.debug(
					"Retry %s/%s for %s in %.1fs (reason: %s)",
					attempt,
					max_attempts,
					address,
					total_sleep,
					last_exc,
				)
				await asyncio.sleep(total_sleep)
				delay = min(delay * 2, max_delay)
				continue
			# Give up
			raise UpdateFailed(f"Network error fetching '{address}': {last_exc}") from last_exc

		popularity = result.get("current_popularity")
		attributes: dict[str, object] = {
			"maps_name": result.get("name"),
			"address": result.get("address"),
			"popularity_is_live": None,
			"popularity_monday": None,
			"popularity_tuesday": None,
			"popularity_wednesday": None,
			"popularity_thursday": None,
			"popularity_friday": None,
			"popularity_saturday": None,
			"popularity_sunday": None,
		}

		try:
			pop = result.get("populartimes", [])
			attributes["popularity_monday"] = pop[0]["data"] if len(pop) > 0 else None
			attributes["popularity_tuesday"] = pop[1]["data"] if len(pop) > 1 else None
			attributes["popularity_wednesday"] = pop[2]["data"] if len(pop) > 2 else None
			attributes["popularity_thursday"] = pop[3]["data"] if len(pop) > 3 else None
			attributes["popularity_friday"] = pop[4]["data"] if len(pop) > 4 else None
			attributes["popularity_saturday"] = pop[5]["data"] if len(pop) > 5 else None
			attributes["popularity_sunday"] = pop[6]["data"] if len(pop) > 6 else None
		except (KeyError, IndexError, TypeError):
			# Keep attributes None if malformed
			pass

		if popularity is None:
			# Fallback to historical based on current time
			dt = datetime.now()
			weekday_index = dt.weekday()
			hour_index = dt.hour
			try:
				popularity = result["populartimes"][weekday_index]["data"][hour_index]
				attributes["popularity_is_live"] = False
			except (KeyError, IndexError, TypeError) as ex:
				raise UpdateFailed("Historical popularity not available for fallback") from ex
		else:
			attributes["popularity_is_live"] = True

		if isinstance(popularity, (int, float)):
			popularity = max(0, min(100, int(popularity)))

		return {"state": popularity, "attributes": attributes}

	coordinator = DataUpdateCoordinator(
		hass,
		_LOGGER,
		name=f"PopularTimes {entry.title}",
		update_method=_async_update_data,
		update_interval=timedelta(minutes=10),
	)

	# First refresh before setting up entities
	await coordinator.async_config_entry_first_refresh()

	# Keep the entry title in sync with the configured Name (options preferred)
	desired_title = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, entry.title))
	if desired_title and entry.title != desired_title:
		# Avoid triggering an extra reload cycle when we update the title
		domain_data["skip_next_reload"] = True
		hass.config_entries.async_update_entry(entry, title=desired_title)

	# Store coordinator for platform setup
	domain_data[entry.entry_id] = {"coordinator": coordinator, **domain_data.get(entry.entry_id, {})}

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	# Listen for options/data updates to propagate to entities and keep title synced
	entry.async_on_unload(entry.add_update_listener(_async_update_listener))
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
	# Cleanup coordinator
	if ok:
		domain_data = hass.data.setdefault(DOMAIN, {})
		domain_data.pop(entry.entry_id, None)
	return ok


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
