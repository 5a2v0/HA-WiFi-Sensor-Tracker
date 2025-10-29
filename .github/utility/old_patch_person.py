"""Patch per modificare la logica di aggiornamento di Person in Home Assistant."""
import logging
import inspect
import hashlib
from homeassistant.core import callback
from homeassistant.components.person import Person, _get_latest
from homeassistant.components.device_tracker import (
    ATTR_SOURCE_TYPE,
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SourceType,
)

# ENTITY_ID_HOME è disponibile solo da HA 2025.9.0 in poi, questo serve per rendere la patch compatibile con versioni vecchie >= 2024.5.0
try:
    from homeassistant.components.zone import ENTITY_ID_HOME
except ImportError:
    ENTITY_ID_HOME = "zone.home"

from homeassistant.const import (
    ATTR_EDITABLE,
    ATTR_GPS_ACCURACY,
    ATTR_ID,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_NAME,
    CONF_ID,
    CONF_NAME,
    EVENT_HOMEASSISTANT_START,
    SERVICE_RELOAD,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

CONF_DEVICE_TRACKERS = "device_trackers"
IGNORE_STATES = (STATE_UNKNOWN, STATE_UNAVAILABLE)

# HASH calcolato a partire dal decoratore @callback della funzione comprensivo degli spazi di indentazione
REFERENCE_HASHES = {
    "2024.5.0+": "bad046c4e122478d12e8b59a2e506cfeb4cb5a63",
    "2025.7.0+": "7751a7e55d376546784156638cfa4d25b0875c35",
    "2025.9.0+": "03003c1662579b5895e9741177ab7aebf2631179",
}


_LOGGER = logging.getLogger(__package__)


def _get_function_hash(func) -> str:
    """Calcola l’hash SHA1 del codice sorgente di una funzione."""
    try:
        src = inspect.getsource(func)
        return hashlib.sha1(src.encode("utf-8")).hexdigest()
    except Exception as e:
        _LOGGER.warning("Impossibile calcolare hash per %s: %s", func, e)
        return ""


def apply_person_patch():
    """Applica la patch solo se la funzione Person._update_state è compatibile."""
    current_hash = _get_function_hash(Person._update_state)

    if current_hash not in REFERENCE_HASHES.values():
        _LOGGER.warning(
            "Versione Person del core non compatibile (HASH = %s). "
            "Patch NON applicata. Attendere aggiornamento integrazione o aggiornare Home Assistant.",
            current_hash,
        )
        return

    # la funzione del core è una versione conosciuta, possiamo applicare la patch
    Person._update_state = _update_state_custom
    _LOGGER.debug("Patch Person applicata correttamente (HASH = %s).", current_hash)


@callback
def _update_state_custom(self) -> None:
    """Update the state."""
    latest_non_gps_home = latest_non_gps_zone = latest_not_home = latest_gps = latest = coordinates = None
    for entity_id in self._config[CONF_DEVICE_TRACKERS]:
        state = self.hass.states.get(entity_id)

        if not state or state.state in IGNORE_STATES:
            continue

        if state.attributes.get(ATTR_SOURCE_TYPE) == SourceType.GPS:
            latest_gps = _get_latest(latest_gps, state)
        elif state.state == STATE_HOME:
            latest_non_gps_home = _get_latest(latest_non_gps_home, state)
        elif state.state not in (STATE_HOME, STATE_NOT_HOME):
             latest_non_gps_zone = _get_latest(latest_non_gps_zone, state)
        else:
            latest_not_home = _get_latest(latest_not_home, state)

    if latest_non_gps_home:
        latest = latest_non_gps_home
        if (
            latest_non_gps_home.attributes.get(ATTR_LATITUDE) is None
            and latest_non_gps_home.attributes.get(ATTR_LONGITUDE) is None
            and (home_zone := self.hass.states.get(ENTITY_ID_HOME))
        ):
            coordinates = home_zone
        else:
            coordinates = latest_non_gps_home
    elif latest_non_gps_zone:
        latest = latest_non_gps_zone
        coordinates = latest_non_gps_zone
    elif latest_gps:
        latest = latest_gps
        coordinates = latest_gps
    else:
        latest = latest_not_home
        coordinates = latest_not_home

    if latest and coordinates:
        self._parse_source_state(latest, coordinates)
    else:
        self._attr_state = None
        self._source = None
        self._latitude = None
        self._longitude = None
        self._gps_accuracy = None

    self._update_extra_state_attributes()
    self.async_write_ha_state()
