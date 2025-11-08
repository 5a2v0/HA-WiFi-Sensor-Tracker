# Patch per modificare la logica di aggiornamento di Person in Home Assistant.
import logging
import inspect
import hashlib
import textwrap
import re
from homeassistant.core import State, callback
from typing import Optional
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_GPS_ACCURACY,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.components.person import (
    CONF_DEVICE_TRACKERS,
    IGNORE_STATES,
    Person,
    _get_latest,
)
from homeassistant.components.device_tracker import (
    ATTR_SOURCE_TYPE,
    SourceType,
)
from homeassistant.components.zone import ENTITY_ID_HOME

# Costante da impostare a True nel caso in cui venisse accettata la PR al core di Home Assistant ed uscisse quindi una nuova versione che non necessita le patch
CORE_ALREADY_UPDATED = False
# Costante da impostare a True se venisse accettata solo parzialmente la PR al core volessi forzare il nascondere l'attributo gps accuracy dal tracker
WORKAROUND_HIDE_GPS_ACCURACY = False


# HASH delle versioni che necessitano di patch calcolati a partire dal decoratore @callback delle funzioni comprensivo degli spazi di indentazione e riga finale vuota
REFERENCE_HASHES = {
    "_update_state": {
        "2020.12.0+": "52a9698a456efe17bbcf7fa0185a7031f759a143",
        "2022.9.0+":  "ea54bac9737ee3d4e69b914518cc8652a8c5c848",
        "2024.2.0+":  "82636f83ba7ea4e8e7f15810e4d67d2fea57526c",
        "2024.5.0+":  "bad046c4e122478d12e8b59a2e506cfeb4cb5a63",
        "2025.7.0+":  "7751a7e55d376546784156638cfa4d25b0875c35",
        "2025.9.0+":  "03003c1662579b5895e9741177ab7aebf2631179",
    },
    "_parse_source_state": {
        "2020.12.0+": "f04d0b99840793ccb2baabce97b74fbf28d838cc",
        "2024.2.0+":  "12bd43983aa84d5a07dd7b0d379ec8b26b4e8c3b",
        "2024.5.0+":  "49765039bb0f610476f53ea4fbffb4272eff7a9f",
        "2025.9.0+":  "82112bc96ed78526273c9873913947e60ef8a9b0",
    }
}


_LOGGER = logging.getLogger(__package__)


def _get_function_hash(func) -> str:
    # Calcola l’hash SHA1 del codice sorgente di una funzione.
    try:
        src = inspect.getsource(func)
        return hashlib.sha1(src.encode("utf-8")).hexdigest()
    except Exception as e:
        _LOGGER.warning("Impossibile calcolare hash per %s: %s", func, e)
        return ""


def _modify_update_state(func_code: str) -> str:
    # Aggiunge la variabile latest_non_gps_zone e i blocchi elif che ne gestiscono la priorità
    lines = func_code.splitlines()

    variable_added = False
    elif_state_added = False
    elif_zone_added = False
    add_coordinates = False
    elif_zone_coordinates = False

    # Check se le modifiche esistono già
    for line in lines:
        if "latest_non_gps_zone" in line:
            variable_added = True
        if "elif state.state not in (STATE_HOME, STATE_NOT_HOME):" in line:
            elif_state_added = True
        if "elif latest_non_gps_zone:" in line:
            elif_zone_added = True

        if "coordinates =" in line:
            add_coordinates = True

    if variable_added and elif_state_added and elif_zone_added:
        return func_code  # Patch già presente, nulla da fare

    new_lines = []
    for i, line in enumerate(lines):
        new_lines.append(line)

        # Inseriamo la nuova variabile subito dopo la dichiarazioni delle variabili note
        if not variable_added and "latest_non_gps_home" in line and "latest_not_home" in line and "latest_gps" in line:
            indent = re.match(r"(\s*)", line).group(1)
            new_lines.append(f"{indent}latest_non_gps_zone = None")
            variable_added = True

        # Inseriamo il piccolo elif subito dopo la riga di latest_non_gps_home
        if not elif_state_added and "latest_non_gps_home = _get_latest(latest_non_gps_home, state)" in line:
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


def _modify_parse_source_state(func_code: str) -> str:
    # Aggiunge il blocco if che nasconde l'attributo GPS_ACCURACY
    lines = func_code.splitlines()

    # Check se il blocco if SourceType.GPS esiste già
    if any("if state.attributes.get(ATTR_SOURCE_TYPE) == SourceType.GPS:" in line for line in lines):
        return func_code  # Patch già presente, nulla da fare

    if_added = False

    for i, line in enumerate(lines):
        if "_gps_accuracy" in line:
            indent = re.match(r"(\s*)", lines[i]).group(1)
            new_lines = [
                f"{indent}if state.attributes.get(ATTR_SOURCE_TYPE) == SourceType.GPS:",
                f"{indent}    self._gps_accuracy = state.attributes.get(ATTR_GPS_ACCURACY)",
                f"{indent}else:",
                f"{indent}    self._gps_accuracy = None",
            ]

            # inseriamo il blocco modificato al posto della riga originale
            patched_lines = lines[:i] + new_lines + lines[i+1:]

            if_added = True

    # Controlli di coerenza finale
    if not if_added:
        raise RuntimeError("Patch Person: blocco if _gps_accuracy non aggiunto — struttura inattesa.")
        
    return "\n".join(patched_lines)


def _patch_update_state():
    original_code = inspect.getsource(Person._update_state)
    # rimuove l'indentazione eccessiva in comune a tutte le righe perchè importata da dentro una classe
    original_code = textwrap.dedent(original_code)
    patched_code = _modify_update_state(original_code)

    if patched_code != original_code:
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


def _patch_parse_source_state():
    original_code = inspect.getsource(Person._parse_source_state)
    # rimuove l'indentazione eccessiva in comune a tutte le righe perchè importata da dentro una classe
    original_code = textwrap.dedent(original_code)
    patched_code = _modify_parse_source_state(original_code)

    if patched_code != original_code:
        # Compila la stringa patchata in un oggetto funzione eseguibile
        local_vars = {}
        exec(patched_code, globals(), local_vars)

        # Recupera l'oggetto funzione dal contesto locale
        patched_func = local_vars.get("_parse_source_state")
        if not patched_func:
            _LOGGER.warning("Patch Person: exec riuscito, ma _parse_source_state non trovata.")
            return
        # Sostituisci la funzione originale con quella patchata
        Person._parse_source_state = patched_func


def apply_person_patch():
    # Applica la patch solo se le funzioni Person._update_state e _parse_source_state sono compatibili e necessarie.
    monitored_functions = {
        "_update_state": Person._update_state,
        "_parse_source_state": Person._parse_source_state,
    }

    compatible = {}
    for func_name, func_ref in monitored_functions.items():
        current_hash = _get_function_hash(func_ref)
        if current_hash in REFERENCE_HASHES[func_name].values():
            compatible[func_name] = True
        else:
            compatible[func_name] = False

    # Tutte compatibili → applica patch completa
    if all(compatible.values()):
        _patch_update_state()
        _patch_parse_source_state()
        _LOGGER.debug("Patch Person applicata/e correttamente.")

    # Nessuna compatibile → blocca patching, avvisa solo se il core non è già stato aggiornato con le modifiche necessarie
    elif not any(compatible.values()):
        if not CORE_ALREADY_UPDATED:
            _LOGGER.warning("Versione del componente Person del core non compatibile, patch NON applicata. Attendere aggiornamento integrazione.")

    # Caso misto → applicazione parziale
    else:
        if compatible["_update_state"]:
            _patch_update_state()
            global WORKAROUND_HIDE_GPS_ACCURACY
            WORKAROUND_HIDE_GPS_ACCURACY = True
            _LOGGER.debug("Patch Person applicata parzialmente. L'attributo GPS precision verrà nascosto tramite indicazione del campo a None")
