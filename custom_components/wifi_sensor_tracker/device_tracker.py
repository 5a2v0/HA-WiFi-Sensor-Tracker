"""Device tracker per Wi-Fi Sensor Tracker."""
import logging
from datetime import timedelta
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Crea le entità tracker dai sensori selezionati nel config entry."""
    ssid_home = entry.data["home_wifi_ssid"]
    sensors = entry.data["sensors"]
    consider_home = entry.data.get("consider_home", 180)

    entities = [
        WifiSensorTrackerEntity(hass, sensor, ssid_home, consider_home)
        for sensor in sensors
    ]
    async_add_entities(entities)


class WifiSensorTrackerEntity(TrackerEntity):
    """Rappresentazione di un tracker Wi-Fi basato su sensore."""

    def __init__(self, hass, sensor, ssid_home, consider_home):
        self.hass = hass
        self._sensor = sensor
        self._ssid_home = ssid_home
        self._attr_name = sensor.replace("sensor.", "").replace(".", "_").replace("_connection", "")
        self._attr_unique_id = sensor.replace("sensor.", "").replace(".", "_").replace("_connection", "")
        self._attr_should_poll = False
        self._attr_is_connected = False
        self._consider_home = timedelta(seconds=consider_home)
        self._remove_listener = None
        self._exit_timer = None  # inizializza il timer

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def state(self):
        return "home" if self._attr_is_connected else "not_home"

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

        if state.state == self._ssid_home:
            self._attr_is_connected = True
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
