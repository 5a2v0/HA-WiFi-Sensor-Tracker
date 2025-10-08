"""Wi-Fi Sensor Tracker integration."""
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
import asyncio

DOMAIN = "wifi_sensor_tracker"
PLATFORMS = ["device_tracker"]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional("home_wifi_ssid"): cv.string,
                vol.Optional("sensors"): [cv.entity_id],
                vol.Optional("consider_home", default=180): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

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

    # Aggiunta del listener per invio automatico request_location_update
    @callback
    def _on_ha_started(event):
        hass.loop.create_task(_send_location_update(hass))

    hass.bus.async_listen_once("homeassistant_started", _on_ha_started)

    return True


async def _send_location_update(hass: HomeAssistant):
    """Invia request_location_update a tutti i mobile_app registrati dopo 30s dall'avvio."""
    await asyncio.sleep(30)
    _LOGGER.info("Invio request_location_update a tutti i Companion App registrati...")

    notify_services = [
        srv for srv in hass.services.async_services().get("notify", {}).keys()
        if srv.startswith("mobile_app_")
    ]

    if not notify_services:
        _LOGGER.warning("Nessun servizio notify.mobile_app_* trovato.")
        return

    for srv in notify_services:
        _LOGGER.debug("Invio request_location_update a %s", srv)
        try:
            await hass.services.async_call(
                "notify",
                srv,
                {"message": "request_location_update"},
                blocking=False,
            )
        except Exception as e:
            _LOGGER.error("Errore nell'inviare update a %s: %s", srv, e)

    _LOGGER.info("Richieste di update inviate a %d dispositivi", len(notify_services))


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
