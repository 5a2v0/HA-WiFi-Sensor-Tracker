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

_LOGGER = logging.getLogger(__package__)

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

    @callback
    def _on_ha_started(event):
        hass.async_create_task(_send_location_update_and_check_sensors(hass, entry))
    # Se Home Assistant è già avviato (es. reload manuale)
    if hass.is_running:
        hass.async_create_task(_send_location_update_and_check_sensors(hass, entry))
    else:
        hass.bus.async_listen_once("homeassistant_started", _on_ha_started)
    
    return True
    

async def _send_location_update_and_check_sensors(hass: HomeAssistant, entry: ConfigEntry):
    """Dopo 30s invia request_location_update e controlla i sensori configurati."""
    await asyncio.sleep(30)
    _LOGGER.debug("Avvio controllo sensori ed invio request_location_update...")
    
    # === INVIO request_location_update ===
    notify_services = [
        srv for srv in hass.services.async_services().get("notify", {}).keys()
        if srv.startswith("mobile_app_")
    ]

    if not notify_services:
        _LOGGER.warning("Nessun dispositivo utilizza l'app companion e condivide quindi sensori compatibili con l'integrazione.")
    else:
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
        _LOGGER.debug("Richieste di update inviate a %d dispositivi", len(notify_services))

    # === CONTROLLO SENSORI ===
    all_sensors = [e for e in hass.states.async_entity_ids("sensor")]
    available_sensors = {
        s for s in all_sensors if s.endswith("_wifi_connection") or s.endswith("_ssid") or s.endswith("_wi_fi_connection")
    }
    
    configured_sensors = set(entry.data.get("sensors", []))

    _LOGGER.debug(
        "Sensori già configurati: %s",
        ", ".join(sorted(configured_sensors)),
    )

    missing_sensors = configured_sensors - available_sensors
    if missing_sensors:
        _LOGGER.warning(
            "Alcuni sensori configurati non sono più disponibili: %s. Puoi aggiornare la configurazione dell'integrazione per eliminarli e di conseguenza eliminare i tracker collegati.",
            ", ".join(sorted(missing_sensors)),
        )

    new_sensors = available_sensors - configured_sensors
    if new_sensors:
        _LOGGER.warning(
            "Rilevati nuovi sensori Wi-Fi compatibili non ancora configurati: %s. Puoi aggiornare la configurazione dell'integrazione per includerli.",
            ", ".join(sorted(new_sensors)),
        )


async def async_soft_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Soft reload: non elimina entità dal registry, solo ricarica la piattaforma."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry e rimuove le entità associate."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    entity_registry = er.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    if entity_entries:
        for entity_entry in entity_entries:
            _LOGGER.debug(
                "Rimozione entità '%s' creata dal config entry '%s'",
                entity_entry.entity_id,
                entry.entry_id,
            )
            entity_registry.async_remove(entity_entry.entity_id)
    else:
        _LOGGER.debug("Nessuna entità trovata da rimuovere per l'integrazione")

    return unload_ok
