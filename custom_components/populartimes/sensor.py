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
from homeassistant.util import slugify
from homeassistant.helpers import entity_registry as er

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
            _LOGGER.info(
                "YAML configuration ignored; config entry already exists for address '%s'",
                address,
            )
            return

    _LOGGER.warning(
        "YAML configuration for Popular Times is deprecated and will be imported to UI: name='%s', address='%s'",
        name,
        address,
    )

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_NAME: name, CONF_ADDRESS: address},
    )

    # Notify user (once per startup) that YAML can be removed
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("yaml_migration_notified"):
        # Mark as notified first to avoid any race in quick successive imports
        domain_data["yaml_migration_notified"] = True
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Popular Times: YAML migrated",
                "message": (
                    "Popular Times entries were imported from YAML to the UI. "
                    "You can now remove them from configuration.yaml."
                ),
                # Use a fixed ID so repeated calls update the same notification
                "notification_id": "populartimes_yaml_migration",
            },
            blocking=False,
        )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Popular Times sensor(s) from a config entry."""
    # Prefer values from options when present to reflect edits without needing a reload
    name = entry.options.get(CONF_NAME, entry.data[CONF_NAME])
    address = entry.options.get(CONF_ADDRESS, entry.data[CONF_ADDRESS])

    # Stable unique ID based on the config entry id (not the address), so edits don't create new entities
    stable_unique_id = f"populartimes_{entry.entry_id}"

    # Migrate any pre-existing entity(ies) for this entry to the new unique_id to avoid orphaning
    registry = er.async_get(hass)
    domain = "sensor"
    platform = "populartimes"

    # Legacy unique_ids were derived from the address hash
    legacy_uids: list[str] = []
    for addr in [entry.data.get(CONF_ADDRESS), entry.options.get(CONF_ADDRESS)]:
        if addr:
            digest = hashlib.sha256(addr.encode("utf-8")).hexdigest()[:12]
            legacy_uids.append(f"populartimes_{digest}")

    # If we don't already have an entity with the stable id, migrate a legacy one if present
    stable_entity_id = registry.async_get_entity_id(domain, platform, stable_unique_id)
    if not stable_entity_id:
        for uid in legacy_uids:
            ent_id = registry.async_get_entity_id(domain, platform, uid)
            if ent_id:
                registry.async_update_entity(ent_id, new_unique_id=stable_unique_id)
                stable_entity_id = ent_id
                break

    # Remove any other duplicates for this config entry under the old scheme
    for ent in list(registry.entities.values()):
        if ent.config_entry_id == entry.entry_id and ent.platform == platform and ent.unique_id != stable_unique_id:
            registry.async_remove(ent.entity_id)

    entity = PopularTimesSensor(name, address, stable_unique_id)
    async_add_entities([entity], True)


class PopularTimesSensor(SensorEntity):

    def __init__(self, name: str, address: str, unique_id: str) -> None:
        """Initialize the sensor."""
        self._name = name
        self._address = address
        self._unique_id = unique_id
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
        return self._unique_id

    @property
    def icon(self) -> str:
        """Return a clock icon indicating the current hour.

        Uses a filled clock when live popularity is available, and an outline clock
        when falling back to historical data. The hour hand reflects the local hour.
        """
        try:
            hour = datetime.now().hour % 12
            words = [
                "twelve",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
            ]
            word = words[hour]
            is_live = bool(self._attributes.get("popularity_is_live"))
            suffix = "" if is_live else "-outline"
            return f"mdi:clock-time-{word}{suffix}"
        except Exception:  # pragma: no cover - fallback for safety
            return "mdi:clock-outline"

    @property
    def suggested_object_id(self) -> str | None:
        """Suggest a default object_id derived from the Name.

        Home Assistant uses this only when the entity is first created. Existing
        entities will keep their current entity_id unless manually changed by the user.
        """
        if not self._name:
            return None
        return f"bar_{slugify(self._name)}"

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass. Sync name/address from entry on reloads."""
        entry = self.platform.config_entry  # type: ignore[assignment]
        if entry:
            # Options override data if provided
            self._name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, self._name))
            self._address = entry.options.get(CONF_ADDRESS, entry.data.get(CONF_ADDRESS, self._address))

    async def async_update(self):
        """Asynchronously get the latest data from Google Popular Times off the event loop."""
        try:
            # Build query using friendly name + address (avoid double-prefixing)
            name = (self._name or "").strip()
            address = (self._address or "").strip()
            if name:
                n = name.lower()
                a = address.lower()
                if a.startswith(n) or a.startswith(f"{n},") or a.startswith(f"{n} "):
                    query = address
                else:
                    query = f"{name}, {address}" if address else name
            else:
                query = address

            # Run the blocking network call in an executor to avoid blocking the event loop
            result = await self.hass.async_add_executor_job(
                livepopulartimes.get_populartimes_by_address, query
            )

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