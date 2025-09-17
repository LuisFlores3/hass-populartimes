"""Support for Google Maps Popular Times as a Home Assistant sensor."""
from datetime import datetime, timedelta
import hashlib
import logging

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity, SensorStateClass
from homeassistant.const import CONF_NAME, CONF_ADDRESS
from homeassistant.config_entries import SOURCE_IMPORT
import homeassistant.helpers.config_validation as cv
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout
import voluptuous as vol

import livepopulartimes

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ADDRESS): cv.string,
    }
)

SCAN_INTERVAL = timedelta(minutes=10)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Backward-compat entry point; delegate to async variant."""
    hass.async_create_task(async_setup_platform(hass, config, add_entities, discovery_info))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Migrate YAML-defined sensor to a config entry and stop setting up from YAML."""
    from .const import DOMAIN  # Local import to avoid editor false positives

    name: str = config[CONF_NAME]
    address: str = config[CONF_ADDRESS]

    norm_addr = address.strip().lower()

    # Avoid duplicate entries if already configured (compare normalized address)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_ADDRESS, "").strip().lower() == norm_addr:
            _LOGGER.debug("YAML import skipped; entry already exists for address '%s'", address)
            return

    _LOGGER.debug("Starting YAML -> UI import for Popular Times: name='%s', address='%s'", name, address)

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_NAME: name, CONF_ADDRESS: address},
    )

    # Notify user that YAML can be removed
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": "Popular Times migrated",
            "message": (
                f"Imported '{name}' from YAML to UI config. "
                "You can now remove it from configuration.yaml."
            ),
        },
        blocking=False,
    )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Popular Times sensor(s) from a config entry."""
    name = entry.data[CONF_NAME]
    address = entry.data[CONF_ADDRESS]
    entity = PopularTimesSensor(name, address)
    async_add_entities([entity], True)


class PopularTimesSensor(SensorEntity):

    def __init__(self, name: str, address: str) -> None:
        """Initialize the sensor."""
        self._name = name
        self._address = address
        self._state: int | None = None

        self._attributes: dict[str, object] = {
            "maps_name": None,
            "address": None,
            "popularity_is_live": None,
            "popularity_monday": None,
            "popularity_tuesday": None,
            "popularity_wednesday": None,
            "popularity_thursday": None,
            "popularity_friday": None,
            "popularity_saturday": None,
            "popularity_sunday": None,
        }

    @property
    def name(self):
        return self._name

    @property
    def native_value(self):
        """Return the current popularity as the sensor value."""
        return self._state

    # Back-compat for older HA versions that still access state
    @property
    def state(self):  # pragma: no cover - compatibility shim
        return self._state
    
    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        return "%"

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this sensor instance."""
        digest = hashlib.sha256(self._address.encode("utf-8")).hexdigest()[:12]
        return f"populartimes_{digest}"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:chart-bar"

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass. Sync name/address from entry on reloads."""
        entry = self.platform.config_entry  # type: ignore[assignment]
        if entry:
            self._name = entry.data.get(CONF_NAME, self._name)
            self._address = entry.data.get(CONF_ADDRESS, self._address)

    def update(self):
        """Get the latest data from Google Popular Times (via livepopulartimes)."""
        try:
            result = livepopulartimes.get_populartimes_by_address(self._address)
            if not result:
                _LOGGER.warning("No data returned for address '%s'", self._address)
                return

            popularity = result.get("current_popularity")

            # Attributes: core metadata
            self._attributes["address"] = result.get("address")
            self._attributes["maps_name"] = result.get("name")

            # Historical data by weekday
            try:
                pop = result.get("populartimes", [])
                self._attributes["popularity_monday"] = pop[0]["data"] if len(pop) > 0 else None
                self._attributes["popularity_tuesday"] = pop[1]["data"] if len(pop) > 1 else None
                self._attributes["popularity_wednesday"] = pop[2]["data"] if len(pop) > 2 else None
                self._attributes["popularity_thursday"] = pop[3]["data"] if len(pop) > 3 else None
                self._attributes["popularity_friday"] = pop[4]["data"] if len(pop) > 4 else None
                self._attributes["popularity_saturday"] = pop[5]["data"] if len(pop) > 5 else None
                self._attributes["popularity_sunday"] = pop[6]["data"] if len(pop) > 6 else None
            except (KeyError, IndexError, TypeError):
                _LOGGER.debug("Historical popularity data missing or malformed for '%s'", self._address)

            # Fallback to historical if live is unavailable
            if popularity is None:
                dt = datetime.now()
                weekday_index = dt.weekday()
                hour_index = dt.hour
                try:
                    historical_data_for_hour = result["populartimes"][weekday_index]["data"][hour_index]
                    popularity = historical_data_for_hour
                    self._attributes["popularity_is_live"] = False
                    _LOGGER.info(
                        "Using historical popularity (no live data) for '%s'", self._address
                    )
                except (KeyError, IndexError, TypeError):
                    _LOGGER.warning(
                        "Historical popularity not available to fallback for '%s'", self._address
                    )
                    return
            else:
                self._attributes["popularity_is_live"] = True

            # Clamp value range to 0..100 just in case
            if isinstance(popularity, (int, float)):
                popularity = max(0, min(100, int(popularity)))

            self._state = popularity

        except (ConnectError, HTTPError, Timeout) as req_err:
            _LOGGER.warning("Network error while fetching popularity for '%s': %s", self._address, req_err)
        except Exception:  # noqa: BLE001 - log unexpected exceptions with stack
            _LOGGER.exception("Unexpected error while updating Popular Times for '%s'", self._address)