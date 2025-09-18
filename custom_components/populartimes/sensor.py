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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

    # Wire up coordinator from domain data (created in __init__.py)
    from .const import DOMAIN  # local import
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    entity = PopularTimesSensor(coordinator, name, address, stable_unique_id)
    async_add_entities([entity], True)


class PopularTimesSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, name: str, address: str, unique_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
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
        """Return the current popularity as the sensor value (cached)."""
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
        # Initialize from coordinator if data available
        data = getattr(self.coordinator, "data", None) if hasattr(self, "coordinator") else None
        if isinstance(data, dict):
            state = data.get("state")
            if isinstance(state, (int, float)):
                self._state = int(state)
            attrs = data.get("attributes") or {}
            self._attributes.update(attrs)

    @property
    def available(self) -> bool:
        """Return True if last coordinator update was successful."""
        if hasattr(self, "coordinator") and self.coordinator is not None:
            return bool(getattr(self.coordinator, "last_update_success", True))
        return True

    def _handle_coordinator_update(self) -> None:
        """Update cached state/attributes from coordinator and write state."""
        data = getattr(self.coordinator, "data", None)
        if isinstance(data, dict):
            state = data.get("state")
            if isinstance(state, (int, float)):
                self._state = int(state)
            attrs = data.get("attributes") or {}
            self._attributes.update(attrs)
        self.async_write_ha_state()

    # Updates are handled by the DataUpdateCoordinator; no per-entity async_update needed