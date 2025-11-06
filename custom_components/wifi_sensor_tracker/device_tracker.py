"""Device tracker per Wi-Fi Sensor Tracker (multi-zona, con consider_home)."""
import logging
from datetime import timedelta
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.util import dt as dt_util
from homeassistant.const import ATTR_FRIENDLY_NAME

_LOGGER = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Crea le entità tracker dai sensori selezionati nel config entry."""
    ssid_home = entry.data["home_wifi_ssid"]
    sensors = entry.data["sensors"]
    consider_home = entry.data.get("consider_home", 180)
    extra_zones = entry.data.get("extra_zones", [])
    
    # Mappa SSID → Nome zona
    ssid_zone_map = {z["ssid"]: z["zone"] for z in extra_zones if "ssid" in z and "zone" in z}

    entities = [
        WifiSensorTrackerEntity(hass, sensor, ssid_home, ssid_zone_map, consider_home)
        for sensor in sensors
    ]
    async_add_entities(entities)


class WifiSensorTrackerEntity(TrackerEntity):
    """Rappresentazione di un tracker Wi-Fi basato su sensore."""

    def __init__(self, hass, sensor, ssid_home, ssid_zone_map, consider_home):
        self.hass = hass
        self._sensor = sensor
        self._ssid_home = ssid_home
        self._attr_name = sensor.replace("sensor.", "").replace(".", "_").replace("_connection", "")
        self._attr_unique_id = sensor.replace("sensor.", "").replace(".", "_").replace("_connection", "")
        self._attr_should_poll = False
        self._attr_is_connected = False
        self._attr_latitude = None
        self._attr_longitude = None
        # Inizializziamo gps_accuracy a None per evitare che il core mostri 0
        #self._attr_gps_accuracy = None
        self._ssid_zone_map = ssid_zone_map or {}
        self._current_zone = "not_home"
        self._consider_home = timedelta(seconds=consider_home)
        self._remove_listener = None
        self._exit_timer = None  # inizializza il timer

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def state(self):
        return self._current_zone if self._attr_is_connected else "not_home"

    @property
    def extra_state_attributes(self):
        """Attributi personalizzati per il tracker Wi-Fi."""
        attrs = {}
        if self._attr_latitude is not None and self._attr_longitude is not None:
            attrs["latitude"] = self._attr_latitude
            attrs["longitude"] = self._attr_longitude
        # Forzo l'attributo None che diventerà null in Json e non verrà mostrato nella UI
        #attrs["gps_accuracy"] = self._attr_gps_accuracy
        return attrs

    def _schedule_exit(self):
        """Programma il cambio di stato dopo il tempo consider_home."""

        # Se c’è già un timer attivo, non crearne un altro
        if self._exit_timer:
            return

        async def _set_not_home(_now):
            self._attr_is_connected = False
            self._exit_timer = None
            self.async_write_ha_state()
            _LOGGER.debug("%s segnato not_home dopo consider_home", self._attr_name)

        # Programma il callback
        self._exit_timer = async_call_later(
            self.hass, self._consider_home, _set_not_home
        )

    async def async_added_to_hass(self):
        """Registra listener e aggiorna immediatamente lo stato iniziale."""

        @callback
        def _sensor_state_listener(event):
            """Aggiorna lo stato dell'entità basandosi sul sensore target."""
            new_state = event.data.get("new_state") if event else None
            self._update_from_sensor(new_state)

        # Listener per il sensore target
        self._remove_listener = async_track_state_change_event(
            self.hass, [self._sensor], _sensor_state_listener
        )

        # Aggiornamento iniziale
        sensor_state = self.hass.states.get(self._sensor)
        self._update_from_sensor(sensor_state)

    def _update_from_sensor(self, state):
        """Applica la logica di aggiornamento."""
        if state is None or state.state in (STATE_UNAVAILABLE, None):
            _LOGGER.debug("Sensore %s non disponibile", self._sensor)
            self._attr_is_connected = False
            self.async_write_ha_state()
            return

        if state.state == self._ssid_home or state.state in self._ssid_zone_map:
            self._attr_is_connected = True
            if state.state == self._ssid_home:
                self._current_zone = "home"
                # Azzeriamo latitude e longitude quando siamo "home"
                self._attr_latitude = None
                self._attr_longitude = None
            else:
                zone_entity_id = self._ssid_zone_map[state.state]
                # se la zona extra è "zone.home", trattala come home
                if zone_entity_id == "zone.home":
                    self._current_zone = "home"
                    # Azzeriamo latitude e longitude quando siamo "home"
                    self._attr_latitude = None
                    self._attr_longitude = None
                else:
                    zone_state = self.hass.states.get(zone_entity_id)
                    if zone_state:
                        # friendly name (es. "Lavoro", "Scuola", ecc.)
                        self._current_zone = zone_state.attributes.get(
                            ATTR_FRIENDLY_NAME, #"friendly_name",
                            zone_entity_id.partition("zone.")[2]
                        )
                        # Aggiorniamo latitude e longitude se la zona è trovata
                        self._attr_latitude = zone_state.attributes.get("latitude")
                        self._attr_longitude = zone_state.attributes.get("longitude")
                    else:
                        # fallback: togli "zone." se presente
                        self._current_zone = zone_entity_id.partition("zone.")[2] or zone_entity_id
                        # Se la zona non esiste, azzeriamo latitude e longitude
                        self._attr_latitude = None
                        self._attr_longitude = None
                        
            self.async_write_ha_state()
            
            # se c’era un timer di uscita → annullalo
            if self._exit_timer:
                self._exit_timer()
                self._exit_timer = None
        else:
            self._schedule_exit()

    async def async_will_remove_from_hass(self):
        """Rimuove il listener e annulla il timer."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._exit_timer:
            self._exit_timer()
            self._exit_timer = None
