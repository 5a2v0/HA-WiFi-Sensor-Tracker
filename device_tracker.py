import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

async def async_setup_scanner(hass: HomeAssistant, config, async_see, discovery_info=None):
    """Set up the custom WiFi tracker."""

    ssid_home = config.get("home_wifi_ssid")
    sensors = config.get("sensors", [])

    if not sensors:
        _LOGGER.error("Nessun sensore specificato per sensor_wifi_tracker")
        return False

    async def update(now=None):
        """Aggiorna lo stato dei tracker basandosi sui sensori WiFi."""
        for sensor in sensors:
            state = hass.states.get(sensor)

            if state is None:
                _LOGGER.warning("Sensore %s non trovato (ancora non disponibile?)", sensor)
                continue  # passa al prossimo sensore senza bloccare tutto

            ssid = state.state
            if ssid == ssid_home:
                location = "home"
            elif not ssid or ssid in ("unknown", "unavailable"):
                location = "not_home"
            else:
                location = "not_home"

            # crea dev_id senza "sensor." e con _ al posto dei punti
            dev_id = sensor.replace("sensor.", "").replace(".", "_")
            _LOGGER.debug("Aggiorno tracker %s → %s", dev_id, location)

            await async_see(
                dev_id=dev_id,
                host_name=sensor,
                location_name=location,
            )

    # 🔹 primo update ritardato di 30s (per dare tempo ai sensori di caricarsi)
    hass.loop.call_later(30, lambda: hass.async_create_task(update()))

    # 🔹 aggiornamento ogni 30s
    async_track_time_interval(hass, update, timedelta(seconds=30))

    return True
