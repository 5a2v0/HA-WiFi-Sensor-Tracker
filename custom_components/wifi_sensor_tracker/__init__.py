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
        if not any(entry.domain == DOMAIN for entry in hass.config_entries.async_entries(DOMAIN)):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "import"},
                    data=config[DOMAIN],
                )
            )
            _LOGGER.warning(
                 "La configurazione YAML per '%s' è stata importata correttamente. "
                 "Puoi ora rimuovere o commentare le righe dal tuo configuration.yaml.",
                 DOMAIN,
            )
        else:
            _LOGGER.warning("È già presente un config entry per %s, la configurazione YAML è ignorata.", DOMAIN)

    # WORKAROUND IN ATTESA DELLA MODIFICA DEL CORE
    try:
        from .patch_person import apply_person_patch
        apply_person_patch()
    except Exception as e:
        _LOGGER.warning("Patch Person: errore nell'importazione o applicazione: %s", e)

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

    # === CONTROLLO ZONE CONFIGURATE ===
    extra_zones = entry.data.get("extra_zones", [])
    if extra_zones:

        # Ottieni tutte le zone esistenti in HA
        ha_zone_states = hass.states.async_all("zone")
        # mapping friendly_name → entity_id
        friendly_to_entity = {z.attributes.get("friendly_name", ""): z.entity_id for z in ha_zone_states}
        # set di entity_id esistenti
        ha_entity_ids = {z.entity_id for z in ha_zone_states}

        # Controllo / migrazione delle zone salvate nell'entry
        updated = False
        for z in extra_zones:
            zone_val = z.get("zone", "")
            # se non è entity_id valido e corrisponde a friendly name, migra
            if not zone_val.startswith("zone.") and zone_val in friendly_to_entity:
                z["zone"] = friendly_to_entity[zone_val]
                updated = True
                _LOGGER.debug("Migrata zona '%s' → '%s' nell'entry", zone_val, z["zone"])

        # aggiorna entry solo se ci sono stati cambiamenti
        if updated:
            data = dict(entry.data)
            data["extra_zones"] = extra_zones
            hass.config_entries.async_update_entry(entry, data=data)
            _LOGGER.debug("Migrazione delle zone extra vecchio formato completata.")

        # Controllo zone mancanti
        configured_zones = {z["zone"] for z in extra_zones if "zone" in z}
        missing_zones = configured_zones - ha_entity_ids
        if missing_zones:
            _LOGGER.warning(
                "Alcune zone configurate nell'integrazione non esistono in Home Assistant: %s. "
                "Crea queste zone sulla mappa altrimenti il tracker della persona non potrà mostrare il nome della zona",
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
            "La configurazione contiene SSID duplicati: %s. "
            "Questo potrebbe causare comportamenti imprevisti. Apri le impostazioni ed elimina le reti/zone extra con stesso SSID",
            ", ".join(sorted(set(duplicates))),
        )

    # === INVIO request_location_update AI DISPOSITIVI CON APP COMPANION REGISTRATI ===
    await asyncio.sleep(30)
    _LOGGER.debug("Avvio controllo sensori/zone ed invio request_location_update...")
    
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


async def async_soft_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Soft reload: non elimina entità dal registry, solo ricarica la piattaforma."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry e rimuove le entità associate."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
