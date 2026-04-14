"""Popular Times integration."""

from __future__ import annotations

import logging
from datetime import timedelta, datetime
import asyncio
import random
import json

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, CONF_NAME, CONF_ADDRESS
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry as dr

import re
import livepopulartimes  # type: ignore

from .const import (
	DOMAIN,
	OPTION_UPDATE_INTERVAL_MINUTES,
	OPTION_MAX_ATTEMPTS,
	OPTION_BACKOFF_INITIAL_SECONDS,
	OPTION_BACKOFF_MAX_SECONDS,
	OPTION_ICON_MODE,
	OPTION_ICON_MDI,
)
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class PopularTimesCoordinator(DataUpdateCoordinator):
	"""Class to manage fetching Popular Times data from Google Maps."""

	def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
		"""Initialize."""
		self.entry = entry
		interval_min = int(entry.options.get(OPTION_UPDATE_INTERVAL_MINUTES, 10))
		interval_min = max(1, min(120, interval_min))

		super().__init__(
			hass,
			_LOGGER,
			name=f"PopularTimes {entry.title}",
			update_interval=timedelta(minutes=interval_min),
		)

	def _parse_duration(self, duration_str: str) -> int | None:
		"""Convert localized duration strings (e.g. '15-45 min', '1 hr') to minutes."""
		if not duration_str or not isinstance(duration_str, str):
			return None

		duration_str = duration_str.lower()
		# Find all numbers (including decimals)
		numbers = re.findall(r"(\d+(?:\.\d+)?)", duration_str)
		if not numbers:
			return None

		# Detect multiplier
		multiplier = 1
		if "hr" in duration_str or "hour" in duration_str:
			multiplier = 60

		try:
			# Convert and apply multiplier
			values = [float(n) * multiplier for n in numbers]
			# Average if range, otherwise first value
			avg_minutes = sum(values) / len(values)
			return int(round(avg_minutes))
		except (ValueError, ZeroDivisionError):
			return None

	async def _async_update_data(self) -> dict:
		"""Fetch data from Google Maps."""
		name = self.entry.options.get(CONF_NAME, self.entry.data.get(CONF_NAME, ""))
		address = self.entry.options.get(CONF_ADDRESS, self.entry.data.get(CONF_ADDRESS, ""))

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

		max_attempts = int(self.entry.options.get(OPTION_MAX_ATTEMPTS, 4))
		delay = float(self.entry.options.get(OPTION_BACKOFF_INITIAL_SECONDS, 1.0))
		max_delay = float(self.entry.options.get(OPTION_BACKOFF_MAX_SECONDS, 8.0))
		last_exc: Exception | None = None
		result = None

		for attempt in range(1, max_attempts + 1):
			try:
				result = await self.hass.async_add_executor_job(
					livepopulartimes.get_populartimes_by_address, query
				)
				if result:
					break
				raise UpdateFailed(f"No data returned for '{address}'")
			except Timeout as req_err:
				last_exc = req_err
				retryable = True
			except ConnectError as req_err:
				last_exc = req_err
				retryable = True
			except json.decoder.JSONDecodeError as req_err:
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
			except UpdateFailed as ex:
				last_exc = ex
				retryable = attempt < max_attempts
			except Exception as ex:  # noqa: BLE001
				raise UpdateFailed(f"Unexpected error fetching '{address}': {ex}") from ex

			if attempt < max_attempts and retryable:
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
			raise UpdateFailed(f"Network error fetching '{address}': {last_exc}") from last_exc

		popularity = result.get("current_popularity")
		attributes: dict[str, object] = {
			"maps_name": result.get("name"),
			"address": result.get("address"),
			"configured_address": address,
			"latitude": None,
			"longitude": None,
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
			lat = None
			lon = None
			coords = (
				result.get("coordinates")
				or result.get("coordinate")
				or result.get("location")
				or result.get("coords")
			)
			if isinstance(coords, dict):
				lat = coords.get("lat") or coords.get("latitude")
				lon = coords.get("lng") or coords.get("lon") or coords.get("longitude")
			elif isinstance(coords, (list, tuple)) and len(coords) >= 2:
				lat, lon = coords[0], coords[1]
			lat = lat if lat is not None else result.get("lat") or result.get("latitude")
			lon = lon if lon is not None else result.get("lng") or result.get("lon") or result.get("longitude")
			if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
				attributes["latitude"] = float(lat)
				attributes["longitude"] = float(lon)
		except Exception:  # pragma: no cover
			pass

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
			pass

		if popularity is None:
			dt = datetime.now()
			weekday_index = dt.weekday()
			hour_index = dt.hour
			try:
				popularity = result["populartimes"][weekday_index]["data"][hour_index]
				attributes["popularity_is_live"] = False
			except (KeyError, IndexError, TypeError):
				_LOGGER.debug("Historical popularity not available for fallback for '%s'", address)
				popularity = 0
		else:
			attributes["popularity_is_live"] = True

		# v3: Additional venue metadata from scraper
		attributes["rating"] = result.get("rating")
		attributes["rating_n"] = result.get("rating_n")
		_LOGGER.warning("RAW WAIT: %s | RAW SPENT: %s", result.get("time_wait"), result.get("time_spent")); attributes["time_wait"] = self._parse_duration(result.get("time_wait"))
		attributes["time_spent"] = self._parse_duration(result.get("time_spent"))

		if isinstance(popularity, (int, float)):
			popularity = max(0, min(100, int(popularity)))

		return {"state": popularity, "attributes": attributes}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Popular Times from a config entry."""
	domain_data = hass.data.setdefault(DOMAIN, {})

	coordinator = PopularTimesCoordinator(hass, entry)

	await coordinator.async_config_entry_first_refresh()

	desired_title = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, entry.title))
	if desired_title and entry.title != desired_title:
		domain_data["skip_next_reload"] = True
		hass.config_entries.async_update_entry(entry, title=desired_title)

	# v3: Register each venue as a Device in the HA Device Registry
	device_reg = dr.async_get(hass)
	device_reg.async_get_or_create(
		config_entry_id=entry.entry_id,
		identifiers={(DOMAIN, entry.entry_id)},
		name=desired_title,
		manufacturer="Popular Times",
		model="Google Maps Scraping",
	)

	domain_data[entry.entry_id] = {"coordinator": coordinator, **domain_data.get(entry.entry_id, {})}

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	entry.async_on_unload(entry.add_update_listener(_async_update_listener))

	if not domain_data.get("service_update_registered"):
		def _validate_str(v):
			return str(v) if v is not None else None

		async def _handle_update_entry(call) -> None:
			entry_id = call.data.get("entry_id")
			if not entry_id:
				_LOGGER.error("populartimes.update_entry called without entry_id")
				return

			cfg = None
			for e in hass.config_entries.async_entries(DOMAIN):
				if e.entry_id == entry_id:
					cfg = e
					break
			if not cfg:
				_LOGGER.error("populartimes.update_entry: entry_id %s not found", entry_id)
				return

			new_opts = dict(cfg.options or {})
			if "name" in call.data:
				new_opts["name"] = _validate_str(call.data.get("name"))
			if "address" in call.data:
				new_opts["address"] = _validate_str(call.data.get("address"))
			if "icon_mode" in call.data:
				new_opts[OPTION_ICON_MODE] = _validate_str(call.data.get("icon_mode"))
			if "icon_mdi" in call.data:
				new_opts[OPTION_ICON_MDI] = _validate_str(call.data.get("icon_mdi"))
			if "update_interval_minutes" in call.data:
				try:
					new_opts[OPTION_UPDATE_INTERVAL_MINUTES] = int(call.data.get("update_interval_minutes"))
				except Exception:
					pass

			hass.config_entries.async_update_entry(cfg, options=new_opts)

		hass.services.async_register(
			DOMAIN,
			"update_entry",
			_handle_update_entry,
		)
		domain_data["service_update_registered"] = True
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
	if ok:
		domain_data = hass.data.setdefault(DOMAIN, {})
		domain_data.pop(entry.entry_id, None)
	return ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Handle config entry updates: sync title and then reload when needed."""
	domain_data = hass.data.setdefault(DOMAIN, {})

	if domain_data.get("skip_next_reload"):
		domain_data["skip_next_reload"] = False
		return

	from homeassistant.const import CONF_NAME as _CONF_NAME
	desired_title = entry.options.get(_CONF_NAME, entry.data.get(_CONF_NAME, entry.title))
	if desired_title and entry.title != desired_title:
		domain_data["skip_next_reload"] = True
		hass.config_entries.async_update_entry(entry, title=desired_title)
		return

	await hass.config_entries.async_reload(entry.entry_id)
