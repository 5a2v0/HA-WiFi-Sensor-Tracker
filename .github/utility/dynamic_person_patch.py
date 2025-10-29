"""Patch per modificare la logica di aggiornamento di Person in Home Assistant."""
import logging
import inspect
import hashlib
#import ast
import textwrap
import re
from homeassistant.core import callback
from homeassistant.components.person import Person, _get_latest
from homeassistant.components.device_tracker import (
    ATTR_SOURCE_TYPE,
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SourceType,
)

# ENTITY_ID_HOME è disponibile solo in versioni recenti di HA, questo serve per rendere la patch compatibile con versioni < 2025.9.0
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


# HASH calcolati a partire dal decoratore @callback della funzione comprensivo degli spazi di indentazione
REFERENCE_HASHES = {
    "2020.12.0+": "52a9698a456efe17bbcf7fa0185a7031f759a143",
    "2022.9.0+": "ea54bac9737ee3d4e69b914518cc8652a8c5c848",
    "2024.2.0+": "82636f83ba7ea4e8e7f15810e4d67d2fea57526c",
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


def _add_patch_modifications(func_code: str) -> str:
    """Aggiunge la variabile extra e il piccolo elif in modo robusto."""
    lines = func_code.splitlines()
    new_lines = []

    # Check se la variabile esiste già
    if any("latest_non_gps_zone" in line for line in lines):
        return func_code  # Patch già presente, nulla da fare
    
    variable_added = False
    elif_state_added = False
    elif_zone_added = False

    add_coordinates = any("coordinates =" in line for line in lines)

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Inseriamo la nuova variabile subito dopo una variabile già esistente
        if not variable_added and "latest_non_gps_home" in line and "latest_not_home" in line and "latest_gps" in line:
            indent = re.match(r"(\s*)", line).group(1)
            new_lines.append(f"{indent}latest_non_gps_zone = None")
            variable_added = True

        # Inseriamo il piccolo elif subito dopo la riga di latest_non_gps_home
        if "latest_non_gps_home = _get_latest(latest_non_gps_home, state)" in line:
            # Prendiamo indentazione della riga originale
            orig_indent = re.match(r"(\s*)", line).group(1)
            # L'elif deve avere un livello in meno rispetto a line
            elif_indent = orig_indent[:-4] if len(orig_indent) >= 4 else ""
            new_lines.append(f"{elif_indent}elif state.state not in (STATE_HOME, STATE_NOT_HOME):")
            # La riga con la nuova variabile va indentata dentro l'elif
            new_lines.append(f"{elif_indent}    latest_non_gps_zone = _get_latest(latest_non_gps_zone, state)")
            elif_state_added = True

        #Inseriamo l'altro blocco elif subito prima della riga elif latest_gps:
        if "elif latest_gps:" in line:
            # Trova indentazione coerente con il blocco if/elif
            indent = re.match(r"(\s*)", line).group(1)
            # Aggiungiamo subito prima il nostro blocco
            insert_pos = len(new_lines) - 1
            new_lines.insert(insert_pos, f"{indent}elif latest_non_gps_zone:")
            new_lines.insert(insert_pos + 1, f"{indent}    latest = latest_non_gps_zone")
            if add_coordinates:
                new_lines.insert(insert_pos + 2, f"{indent}    coordinates = latest_non_gps_zone")
            elif_zone_added = True

    # Controlli di coerenza finale
    if not variable_added:
        raise RuntimeError("Patch Person: variabile 'latest_non_gps_zone' non aggiunta — struttura inattesa.")
    if not elif_state_added:
        raise RuntimeError("Patch Person: blocco 'elif state.state not in (...)' non aggiunto — struttura inattesa.")
    if not elif_zone_added:
        raise RuntimeError("Patch Person: blocco 'elif latest_non_gps_zone' non aggiunto — struttura inattesa.")

    return "\n".join(new_lines)


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
    original_code = inspect.getsource(Person._update_state)
    # rimuove l'indentazione eccessiva in comune a tutte le righe perchè importata da dentro una classe
    original_code = textwrap.dedent(original_code)
    patched_code = _add_patch_modifications(original_code)
    
    # Compila la stringa patchata in un oggetto funzione eseguibile
    local_vars = {}
    exec(patched_code, globals(), local_vars)
    
    # Recupera l'oggetto funzione dal contesto locale
    patched_func = local_vars.get("_update_state")
    if not patched_func:
        _LOGGER.warning("Patch Person: exec riuscito, ma _update_state non trovata.")
        return

    # Sostituisci la funzione originale con quella patchata
    Person._update_state = patched_func
    #Person._update_state = _update_state_custom
    _LOGGER.debug("Patch Person applicata correttamente (HASH = %s).", current_hash)




'''
# Vecchia dichiarazione statica della def
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
'''
