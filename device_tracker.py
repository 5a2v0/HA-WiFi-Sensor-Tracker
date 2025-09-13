import logging
from homeassistant.components.device_tracker import SOURCE_TYPE_ROUTER, ScannerEntity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.const import STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

async def async_setup_scanner(hass: HomeAssistantType, config, async_see, discovery_info=None):
    """Set up the custom WiFi tracker."""

    ssid_home = config.get("home_wifi_ssid")
    sensors = config.get("sensors", [])

    if not sensors:
        _LOGGER.error("Nessun sensore specificato per sensor_wifi_tracker")
        return False

    async def update(now=None):
        for sensor in sensors:
            state = hass.states.get(sensor)
            if state is None:
                _LOGGER.warning("Sensore %s non trovato", sensor)
                continue

            ssid = state.state
            if ssid == ssid_home:
                location = "home"
            elif ssid == STATE_UNKNOWN or not ssid:
                location = "not_home"
            else:
                location = "not_home"

            _LOGGER.debug("Aggiorno tracker %s: %s", sensor, location)

            await async_see(
                dev_id=sensor.split(".")[-1],
                host_name=sensor,
                location_name=location,
                source_type=SOURCE_TYPE_ROUTER,
            )

    hass.helpers.event.track_time_interval(update, hass.helpers.event.dt.timedelta(seconds=30))
    await update()
    return True
