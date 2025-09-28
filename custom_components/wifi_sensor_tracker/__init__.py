"""Wi-Fi Sensor Tracker integration."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

DOMAIN = "wifi_sensor_tracker"
PLATFORMS = ["device_tracker"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """YAML setup (legacy)."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=config[DOMAIN],
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and remove its entities."""
    # 1. Unload le piattaforme
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # 2. Pulizia delle entità create da questo ConfigEntry
    entity_registry = er.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    if entity_entries:
        for entity_entry in entity_entries:
            _LOGGER.debug(
                "Removing entity '%s' created by config entry '%s'",
                entity_entry.entity_id,
                entry.entry_id,
            )
            entity_registry.async_remove(entity_entry.entity_id)
    else:
        _LOGGER.debug(
            "No entities found to remove for config entry '%s'", entry.entry_id
        )
    return unload_ok
