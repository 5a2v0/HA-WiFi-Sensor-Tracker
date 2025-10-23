"""Patch per modificare la logica di aggiornamento di PersonEntity in Home Assistant."""
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
from homeassistant.components.zone import ENTITY_ID_HOME
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


REFERENCE_HASH = "03003c1662579b5895e9741177ab7aebf2631179" # HASH calcolato a partire dal decoratore @callback della funzione comprensivo degli spazi di indentazione


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

    if current_hash != REFERENCE_HASH:
        _LOGGER.warning(
            "Versione Person del core non compatibile (%s != %s). "
            "Patch NON applicata. Attendere aggiornamento integrazione.",
            current_hash,
            REFERENCE_HASH,
        )
        return

    # la funzione è identica alla versione testata
    Person._update_state = _update_state_custom
    _LOGGER.debug("Patch Person applicata correttamente (hash %s).", current_hash)


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
