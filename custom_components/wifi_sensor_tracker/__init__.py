"""Wi-Fi Sensor Tracker integration."""
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import __version__ as HA_VERSION
from packaging.version import parse as parse_version
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
import asyncio


DOMAIN = "wifi_sensor_tracker"
PLATFORMS = ["device_tracker"]
MIN_HA_VERSION = "2026.07.0"


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
    """Home Assistant minimum version check"""
    if parse_version(HA_VERSION) < parse_version(MIN_HA_VERSION):
        _LOGGER.warning(
            "Wi-Fi Sensor Tracker requires Home Assistant %s or newer (current version: %s).",
            MIN_HA_VERSION, HA_VERSION,
        )
        # Interrompe il setup se la versione di Home Assistant è troppo vecchia
        return False

    # Patch del componente Person per versioni del core in cui manca la priorità dei tracker stationary rispetto a quelli gps
    try:
        from .patch_person import apply_person_patch
        apply_person_patch()
    except Exception as e:
        _LOGGER.warning("Patch Person: errore nell'importazione o applicazione: %s", e)

    # YAML setup (legacy)
    if DOMAIN in config:
        # Se non esiste un entry lo creo e importo i dati esistenti
        if not any(entry.domain == DOMAIN for entry in hass.config_entries.async_entries(DOMAIN)):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "import"},
                    data=config[DOMAIN],
                )
            )
            _LOGGER.debug(
                 "YAML configuration for '%s' was successfully imported. "
                 "You can now remove or comment it out from your configuration.yaml file.",
                 DOMAIN,
            )
        # Altrimenti ricordo solo che la configurazione Yaml è deprecata
        else:
            _LOGGER.debug("A config entry for '%s' already exists, YAML configuration will be ignored.", DOMAIN)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configuro l'integrazione con i dati del config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Gestisco controlli all'avvio dell'integrazione sia in caso di reload manuale dell'integrazione sia all'avvio di Home Assistant
    if hass.is_running:
        hass.async_create_task(_initial_checks_and_update_request(hass, entry))
    else:
        @callback
        def _on_ha_started(event):
            hass.async_create_task(_initial_checks_and_update_request(hass, entry))
        hass.bus.async_listen_once("homeassistant_started", _on_ha_started)
    return True


async def _initial_checks_and_update_request(hass: HomeAssistant, entry: ConfigEntry):
    """Controlla i sensori, le zone e gli ssid configurate. Dopo 30s invia request_location_update ai dispositivi con app companion registrata"""

    # === CONTROLLO SENSORI ===
    all_sensors = [e for e in hass.states.async_entity_ids("sensor")]
    available_sensors = {
        s for s in all_sensors if s.endswith("_wifi_connection") or s.endswith("_ssid") or s.endswith("_wi_fi_connection")
    }
    configured_sensors = set(entry.data.get("sensors", []))
    missing_sensors = configured_sensors - available_sensors

    if missing_sensors:
        _LOGGER.warning(
            "Some configured sensors are no longer available: %s. You can update the integration configuration to remove them and their related trackers.",
            ", ".join(sorted(missing_sensors)),
        )

    new_sensors = available_sensors - configured_sensors

    if new_sensors:
        _LOGGER.info(
            "New compatible Wi-Fi sensors detected but not yet configured: %s. You can update the integration configuration to include them.",
            ", ".join(sorted(new_sensors)),
        )

    # === CONTROLLO ZONE CONFIGURATE ===
    extra_zones = entry.data.get("extra_zones", [])
    if extra_zones:

        # Ottieni tutte le zone esistenti in HA
        ha_zone_states = hass.states.async_all("zone")
        # Mapping friendly_name → entity_id
        friendly_to_entity = {z.attributes.get("friendly_name", ""): z.entity_id for z in ha_zone_states}
        # Set di entity_id esistenti
        ha_entity_ids = {z.entity_id for z in ha_zone_states}

        # Controllo / migrazione delle zone salvate nell'entry
        updated = False
        for z in extra_zones:
            zone_val = z.get("zone", "")
            # Se non è entity_id valido e corrisponde a friendly name, migra
            if not zone_val.startswith("zone.") and zone_val in friendly_to_entity:
                z["zone"] = friendly_to_entity[zone_val]
                updated = True
                _LOGGER.debug("Zone '%s' migrated to '%s' in the config entry", zone_val, z["zone"])

        # Aggiorna entry solo se ci sono stati cambiamenti
        if updated:
            data = dict(entry.data)
            data["extra_zones"] = extra_zones
            hass.config_entries.async_update_entry(entry, data=data)
            _LOGGER.debug("Legacy extra zones migration completed.")

        # Controllo zone mancanti
        configured_zones = {z["zone"] for z in extra_zones if "zone" in z}
        missing_zones = configured_zones - ha_entity_ids
        if missing_zones:
            _LOGGER.warning(
                "Some configured zones do not exist in Home Assistant: %s. "
                "Create them in the map to allow the Person entity to display the correct zone.",
                ", ".join(sorted(missing_zones)),
            )


    # === CONTROLLO SSID CONFIGURATI ===
    extra_ssid = set()
    duplicates = []
    for z in entry.data.get("extra_zones", []):
        ssid = z.get("ssid")
        if ssid in extra_ssid:
            duplicates.append(ssid)
        else:
            extra_ssid.add(ssid)

    if duplicates:
        _LOGGER.warning(
            "Duplicate SSIDs found in configuration: %s. "
            "This may cause unexpected behavior. Remove duplicate networks or zones from the integration options.",
            ", ".join(sorted(set(duplicates))),
        )

    # === INVIO request_location_update AI DISPOSITIVI CON APP COMPANION REGISTRATI ===
    await asyncio.sleep(30)
    
    notify_services = [
        srv for srv in hass.services.async_services().get("notify", {}).keys()
        if srv.startswith("mobile_app_")
    ]

    if not notify_services:
        _LOGGER.info("No devices with the Home Assistant Companion App providing compatible sensors were found.")
    else:
        for srv in notify_services:
            _LOGGER.debug("Sending location update request to %s", srv)
            try:
                await hass.services.async_call(
                    "notify",
                    srv,
                    {"message": "request_location_update"},
                    blocking=False,
                )
            except Exception as e:
                _LOGGER.error("Failed to send location update request to %s: %s", srv, e)
        _LOGGER.debug("Sent location update requests to %d devices", len(notify_services))


async def async_soft_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Soft reload: non elimina entità dal registry, solo ricarica la piattaforma."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry e rimuove le entità associate."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
