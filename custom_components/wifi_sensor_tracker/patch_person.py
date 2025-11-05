"""Patch per modificare la logica di aggiornamento di Person in Home Assistant."""
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

CORE_ALREADY_UPDATED = False

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


def _patch_update_state(func_code: str) -> str:
    """Aggiunge la variabile extra e il piccolo elif in modo robusto."""
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
        if "latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None" in line:
            elif_zone_coordinates = True
        if "coordinates =" in line:
            add_coordinates = True

    if variable_added and elif_state_added and elif_zone_added and elif_zone_coordinates:
        return func_code  # Patch già presente, nulla da fare

    new_lines = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
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
        if not elif_zone_added and "elif latest_gps:" in line:
            # Trova indentazione coerente con il blocco if/elif
            indent = re.match(r"(\s*)", line).group(1)
            # Aggiungiamo subito prima il nostro blocco
            insert_pos = len(new_lines) - 1
            new_lines.insert(insert_pos, f"{indent}elif latest_non_gps_zone:")
            new_lines.insert(insert_pos + 1, f"{indent}    latest = latest_non_gps_zone")
            if add_coordinates:
                new_lines.insert(insert_pos + 2, f"{indent}    if (")
                new_lines.insert(insert_pos + 3, f"{indent}        latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None")
                new_lines.insert(insert_pos + 4, f"{indent}        and latest_non_gps_zone.attributes.get(ATTR_LONGITUDE) is None")
                new_lines.insert(
                    insert_pos + 5,
                    indent + '        and (zone := self.hass.states.get(f"zone.{latest_non_gps_zone.state.lower().replace(\' \', \'_\')}"))'
                )
                new_lines.insert(insert_pos + 6, f"{indent}    ):")
                new_lines.insert(insert_pos + 7, f"{indent}        coordinates = zone")
                new_lines.insert(insert_pos + 8, f"{indent}    else:")
                new_lines.insert(insert_pos + 9, f"{indent}        coordinates = latest_non_gps_zone")
            elif_zone_added = True
            elif_zone_coordinates = True

        #Se invece l'ultimo blocco elif esiste ma non ha il check sulle coordinate
        elif elif_zone_added and add_coordinates and not elif_zone_coordinates and "latest = latest_non_gps_zone" in line:
            indent = re.match(r"(\s*)", line).group(1)
            # Controlla se la prossima riga è quella da sostituire
            if i + 1 < len(lines) and "coordinates = latest_non_gps_zone" in lines[i + 1]:
                # Inserisci il blocco completo invece della riga semplice
                new_lines.append(f"{indent}if (")
                new_lines.append(f"{indent}    latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None")
                new_lines.append(f"{indent}    and latest_non_gps_zone.attributes.get(ATTR_LONGITUDE) is None")
                new_lines.append(indent + f'    and (zone := self.hass.states.get(f"zone.{latest_non_gps_zone.state.lower().replace(" ", "_")}"))')
                new_lines.append(f"{indent}):")
                new_lines.append(f"{indent}    coordinates = zone")
                new_lines.append(f"{indent}else:")
                new_lines.append(f"{indent}    coordinates = latest_non_gps_zone")
                elif_zone_coordinates = True
                skip_next = True


    # Controlli di coerenza finale
    if not variable_added:
        raise RuntimeError("Patch Person: variabile 'latest_non_gps_zone' non aggiunta — struttura inattesa.")
    if not elif_state_added:
        raise RuntimeError("Patch Person: blocco 'elif state.state not in (...)' non aggiunto — struttura inattesa.")
    if not elif_zone_added or not elif_zone_coordinates:
        raise RuntimeError("Patch Person: blocco 'elif latest_non_gps_zone' non aggiunto/modificato — struttura inattesa.")

    return "\n".join(new_lines)


def _patch_parse_source_state(func_code: str) -> str:
    """Aggiunge il piccolo if in modo robusto."""
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


def apply_person_patch():
    """Applica la patch solo se la funzione Person._update_state è compatibile e necessaria."""
    current_hash = _get_function_hash(Person._update_state)
    # se la funzione del core è una versione conosciuta e necessita la patch la applichiamo altrimenti usciamo subito dalla funzione
    if current_hash not in REFERENCE_HASHES.values():
        if not CORE_ALREADY_UPDATED:
            _LOGGER.warning(
                "Versione Person del core non compatibile (HASH = %s). "
                "Patch NON applicata. Attendere aggiornamento integrazione o aggiornare Home Assistant.",
                current_hash,
            )
            return


    ### PATCH UPDATE_STATE
    original_code = inspect.getsource(Person._update_state)
    # rimuove l'indentazione eccessiva in comune a tutte le righe perchè importata da dentro una classe
    original_code = textwrap.dedent(original_code)
    patched_code = _patch_update_state(original_code)

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


    ### PATCH PARSE_SOURCE_STATE
    original_code = inspect.getsource(Person._parse_source_state)
    # rimuove l'indentazione eccessiva in comune a tutte le righe perchè importata da dentro una classe
    original_code = textwrap.dedent(original_code)
    patched_code = _patch_parse_source_state(original_code)

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
    
    _LOGGER.debug("Patch Person applicata/e correttamente o non necessarie (HASH = %s).", current_hash)
