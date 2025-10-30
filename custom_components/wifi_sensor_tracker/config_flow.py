"""Config flow for Wi-Fi Sensor Tracker (multi-step: home + optional extra SSID/Zone)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import selector, SelectSelector, SelectSelectorConfig
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import area_registry as ar
from . import DOMAIN, async_soft_reload_entry


# keys used in temporary storage
_BASE = "base"
_EXTRA_ZONES = "extra_zones"


async def _get_wifi_sensors(hass) -> List[str]:
    """Restituisci la lista di sensori filtrati in base al nome"""
    entity_reg = er.async_get(hass)
    all_entities = [e.entity_id for e in entity_reg.entities.values() if e.entity_id.startswith("sensor.")]
    wifi_sensors = [
        eid for eid in all_entities
        if "_wifi_connection" in eid or "_ssid" in eid or "_wi_fi_connection" in eid
    ]
    return sorted(wifi_sensors)


async def _get_zone_options(hass):
    """Restituisce una lista di zone (value=entity_id, label=friendly_name)."""
    zones = []
    for state in hass.states.async_all("zone"):
        entity_id = state.entity_id
        friendly_name = state.attributes.get("friendly_name", entity_id.split(".", 1)[-1])
        zones.append({"value": entity_id, "label": friendly_name})
    return sorted(zones, key=lambda z: z["label"].lower())


async def _format_extra_zones_preview(hass, extra_zones: List[Dict[str, str]]) -> str:
    """Restituisce una stringa leggibile con SSID → friendly name zona."""
    lines = []
    for z in extra_zones:
        if z.get("delete"):
            continue
        ssid = z.get("ssid", "?")
        zone_entity_id = z.get("zone", "?")
        zone_state = hass.states.get(zone_entity_id)
        if zone_state:
            zone_label = zone_state.attributes.get("friendly_name", zone_entity_id)
        else:
            zone_label = f"{zone_entity_id.partition('zone.')[2]} ⚠"
        lines.append(f"SSID: {ssid} → Zona: {zone_label}")
    return "\n".join(lines) or "Nessuna rete/zone aggiuntiva"


class WifiSensorTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisci il config flow for Wi-Fi Sensor Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        """Inizializza il flow"""
        self._base_config: Dict[str, Any] = {}
        self._extra_zones: List[Dict[str, str]] = []


    async def async_step_import(self, import_config: dict) -> Dict[str, Any]:
        """Importa da eventuale configuration.yaml."""
        return await self.async_step_user(user_input=import_config)


    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Initial step: home SSID, sensors, consider_home, optional add_zone checkbox."""
        errors: Dict[str, str] = {}

        wifi_sensors = await _get_wifi_sensors(self.hass)

        # Mantiene i dati digitati se ci sono errori
        ssid_default = user_input.get("home_wifi_ssid") if user_input else ""
        sensors_default = user_input.get("sensors") if user_input else []
        consider_home_default = user_input.get("consider_home", 180) if user_input else 180
        add_zone_default = user_input.get("add_zone", False) if user_input else False

        schema = vol.Schema(
            {
                vol.Required("home_wifi_ssid", description={"translation_key": "home_wifi_ssid"}, default=ssid_default): str,
                vol.Required(
                    "sensors",
                    description={"translation_key": "sensors"},
                    default=sensors_default,
                ): selector(
                    {
                        "entity": {
                            "multiple": True,
                            "include_entities": wifi_sensors,
                        }
                    }
                ),
                vol.Optional("consider_home", description={"translation_key": "consider_home"}, default=consider_home_default): int,
                vol.Optional("add_zone", description={"translation_key": "add_zone"}, default=add_zone_default): bool,
            }
        )

        if user_input is not None:
            ssid = (user_input.get("home_wifi_ssid") or "").strip()
            sensors = user_input.get("sensors", [])

            if not ssid:
                errors["base"] = "missing_ssid"
            elif len(ssid.encode("utf-8")) > 32:
                errors["base"] = "ssid_too_long"
            elif not sensors:
                errors["base"] = "no_sensors"
            if errors:
                return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

            else:
                # Conservo in memoria l'attuale configurazone base
                self._base_config = {
                    "home_wifi_ssid": user_input["home_wifi_ssid"],
                    "sensors": sensors,
                    "consider_home": user_input.get("consider_home", 180),
                }

                add_zone = user_input.get("add_zone", False)
                if add_zone:
                    # Avvia un flow multi-step per aggiungere extra SSID/zone
                    return await self.async_step_add_zones()

                # Non è stato selezionato il tasto per aggiungere reti extra, salva tutto e termina
                data = dict(self._base_config)
                # Se non è stata configurata alcuna rete extra, crea una lista vuota
                data["extra_zones"] = list(self._extra_zones)
                return self.async_create_entry(title="Wi-Fi Sensor Tracker", data=data)

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


    async def async_step_add_zones(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Step per aggiungere extra SSID / zone (ripetibile)."""
        errors: Dict[str, str] = {}

        zone_options = await _get_zone_options(self.hass)
        zone_options.insert(0, {"value": "", "label": "-"})

        ssid_zone_default = user_input.get("ssid_zone", "") if user_input else ""
        zone_name_default = user_input.get("zone_name", "") if user_input else ""
        add_another_default = user_input.get("add_another", False) if user_input else False

        schema = vol.Schema(
            {
                vol.Optional("ssid_zone", description={"translation_key": "ssid_zone"}, default=ssid_zone_default): str,
                vol.Optional(
                    "zone_name",
                    description={"translation_key": "zone_name"},
                    default=zone_name_default,
                ): selector(
                    {
                        "select": {
                            "options": zone_options,
                            "mode": "dropdown",
                            "custom_value": False,
                        }
                    }
                ),
                vol.Optional("add_another", description={"translation_key": "add_another"}, default=add_another_default): bool,
            }
        )

        if user_input is not None:
            ssid_zone = (user_input.get("ssid_zone") or "").strip()
            zone_entity_id = (user_input.get("zone_name") or "").strip()
            add_another = user_input.get("add_another", False)

            # Schermata nuova rete, nessun ssid e zona inseriti, salva tutto e chiudi
            if not ssid_zone and not zone_entity_id:
                data = dict(self._base_config)
                data["extra_zones"] = list(self._extra_zones)
                return self.async_create_entry(title="Wi-Fi Sensor Tracker", data=data)

            # Se uno è compilato e l'altro no, restituisci errore
            if (not ssid_zone and zone_entity_id) or (ssid_zone and not zone_entity_id):
                if not ssid_zone:
                    errors["base"] = "ssid_missing"
                elif not zone_entity_id:
                    errors["base"] = "zone_missing"
                return self.async_show_form(step_id="add_zones", data_schema=schema, errors=errors)

            # Controlla il nome SSID inserito per la rete
            if len(ssid_zone.encode("utf-8")) > 32:
                errors["base"] = "ssid_too_long"
                return self.async_show_form(step_id="add_zones", data_schema=schema, errors=errors)

            # Recupero SSID principale della configurazione base e le altre eventuali reti per le zone extra già salvate
            home_ssid = self._base_config.get("home_wifi_ssid", "").strip()
            existing_ssids = [home_ssid] + [z["ssid"].strip() for z in self._extra_zones]

            # Evita di inserire un SSID già configurato (case-sensitive, come da standard Wi-Fi)
            if ssid_zone in existing_ssids:
                errors["base"] = "ssid_already_exists"
                return self.async_show_form(step_id="add_zones", data_schema=schema, errors=errors)

            # Se entrambi i campi sono compilati correttamente, memorizza la rete
            self._extra_zones.append({"ssid": ssid_zone, "zone": zone_entity_id})

            if add_another:
                # Mostra un'altro step vuoto
                return await self.async_step_add_zones()

            # Salva tutti i dati nel config entry
            data = dict(self._base_config)
            data["extra_zones"] = list(self._extra_zones)
            return self.async_create_entry(title="Wi-Fi Sensor Tracker", data=data)

        return self.async_show_form(step_id="add_zones", data_schema=schema, errors=errors)


    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler (re-use the options handler already present)."""
        return WifiSensorTrackerOptionsFlowHandler(config_entry)




class WifiSensorTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    """Gestisci il flow di modifica per Wi-Fi Sensor Tracker."""


    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._zones_to_edit: List[Dict[str, str]] = list(self._entry.data.get("extra_zones", []))
        # Pulisce flag "delete" lasciati da un eventual flow interrotto
        for z in self._zones_to_edit:
            if "delete" in z:
                z.pop("delete", None)
        self._current_index = 0


    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Step principale di modifica base."""
        errors: Dict[str, str] = {}

        wifi_sensors = await _get_wifi_sensors(self.hass)

        schema = vol.Schema(
            {
                vol.Required(
                    "home_wifi_ssid",
                    description={"translation_key": "home_wifi_ssid"},
                    default=self._entry.data.get("home_wifi_ssid"),
                ): str,
                vol.Required(
                    "sensors",
                    description={"translation_key": "sensors"},
                    default=self._entry.data.get("sensors", []),
                ): selector(
                    {
                        "entity": {
                            "multiple": True,
                            "include_entities": wifi_sensors,
                        }
                    }
                ),
                vol.Optional(
                    "consider_home",
                    description={"translation_key": "consider_home"},
                    default=self._entry.data.get("consider_home", 180),
                ): int,
                # Mostra una lista delle zone aggiuntive già memorizzate
                vol.Optional(
                    "extra_zones_preview",
                    description={"translation_key": "extra_zones_preview"},
                    default=await _format_extra_zones_preview(self.hass, self._zones_to_edit),
                ): selector(
                    {
                        "text": {
                            "multiline": True,
                        }
                    }
                ),
                vol.Optional(
                    "zone_action",
                    description={"translation_key": "zone_action"},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            "manage",
                            "add"
                        ],
                        mode="dropdown",
                        translation_key="zone_action_option"
                    )
                ),
            }
        )

        if user_input is not None:
            # 1. Valida e calcola differenze 
            new_ssid = (user_input.get("home_wifi_ssid") or "").strip()
            new_sensors = set(user_input.get("sensors", []))
            new_consider_home = user_input.get("consider_home", 180)
            action = user_input.get("zone_action", "none")

            old_ssid = self._entry.data.get("home_wifi_ssid")
            old_sensors = set(self._entry.data.get("sensors", []))
            old_consider_home = self._entry.data.get("consider_home", 180)

            if not new_ssid:
                errors["base"] = "missing_ssid"
            elif len(new_ssid.encode("utf-8")) > 32:
                errors["base"] = "ssid_too_long"
            elif not new_sensors:
                errors["base"] = "no_sensors"
            if errors:
                return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

            else:
                sensors_to_add = new_sensors - old_sensors
                sensors_to_remove = old_sensors - new_sensors
                ssid_changed = new_ssid != old_ssid
                consider_home_changed = new_consider_home != old_consider_home

                # 3. Rimuove le entità dei tracker legati ad eventuali sensori eliminati
                if sensors_to_remove:
                    entity_registry = er.async_get(self.hass)
                    for sensor in sensors_to_remove:
                        entity_id = f"device_tracker.{sensor.replace('sensor.', '').replace('.', '_').replace('_connection', '')}"
                        entry = entity_registry.async_get(entity_id)
                        if entry:
                            entity_registry.async_remove(entry.entity_id)

                # 4 Salva i dati nel config entry
                # Conserva temporaneamente i dati in memoria
                self._base_data = {
                    "home_wifi_ssid": new_ssid,
                    "sensors": list(new_sensors),
                    "consider_home": new_consider_home,
                }

                # Verifica se l'utente ha scelto di gestire le reti extra
                #if manage_zones:
                #    return await self.async_step_edit_zones()
                if action == "manage":
                    self._mode = "manage"
                    return await self.async_step_edit_zones()
                elif action == "add":
                    self._mode = "add"
                    self._current_index = len(self._zones_to_edit)
                    return await self.async_step_edit_zones()

                # Se invece non deve gestire zone, salva la configurazione attuale
                data = dict(self._base_data)
                data["extra_zones"] = list(self._zones_to_edit)
                self.hass.config_entries.async_update_entry(self._entry, data=data)

                # Se sono state fatte modifiche, ricarica l'integrazione
                if sensors_to_add or sensors_to_remove or ssid_changed or consider_home_changed:
                    await async_soft_reload_entry(self.hass, self._entry)

                return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


    async def async_step_edit_zones(self, user_input: Optional[Dict[str, Any]] = None):
        """Permette modifica/eliminazione/aggiunta delle reti/zone extra."""
        errors: Dict[str, str] = {}
        zone_options = await _get_zone_options(self.hass)
        zone_options.insert(0, {"value": "", "label": "-"})

        ssid_zone_default = user_input.get("ssid_zone", "") if user_input else ""
        zone_name_default = user_input.get("zone_name", "") if user_input else ""
        add_another_default = user_input.get("add_another", False) if user_input else False

        # Se abbiamo finito di mostrare tutte le reti esistenti mostriamo form vuoto per eventuale nuova rete
        if self._current_index >= len(self._zones_to_edit):
            if getattr(self, "_mode", "manage") == "manage":
                # Modalità modifica: abbiamo finito di scorrere le reti, salva tutto
                data = dict(self._base_data)
                cleaned = [{"ssid": z["ssid"], "zone": z["zone"]} for z in self._zones_to_edit if not z.get("delete")]
                data["extra_zones"] = cleaned
                self.hass.config_entries.async_update_entry(self._entry, data=data)
                await async_soft_reload_entry(self.hass, self._entry)
                return self.async_create_entry(title="", data={})
            else:
                #Modalità aggiunta, mostriamo form vuoto
                schema = vol.Schema(
                    {
                        vol.Optional("ssid_zone", description={"translation_key": "ssid_zone"}, default=ssid_zone_default): str,
                        vol.Optional(
                            "zone_name",
                            description={"translation_key": "zone_name"},
                            default=zone_name_default,
                        ): selector(
                            {
                                "select": {
                                    "options": zone_options,
                                    "mode": "dropdown",
                                    "custom_value": False,
                                }
                            }
                        ),
                        vol.Optional("add_another", description={"translation_key": "add_another"}, default=add_another_default): bool,
                    }
                )

                if user_input is not None:
                    ssid_zone = (user_input.get("ssid_zone") or "").strip()
                    zone_entity_id = (user_input.get("zone_name") or "").strip()
                    add_another = user_input.get("add_another", False)

                    if not ssid_zone and not zone_entity_id:
                        # Schermata nuova rete, nessuna nuova rete ed ssid inseriti, salva tutto e chiudi
                        data = dict(self._base_data)
                        cleaned = [{"ssid": z["ssid"], "zone": z["zone"]} for z in self._zones_to_edit if not z.get("delete")]
                        data["extra_zones"] = cleaned
                        self.hass.config_entries.async_update_entry(self._entry, data=data)
                        await async_soft_reload_entry(self.hass, self._entry)
                        return self.async_create_entry(title="", data={})

                    # Se uno è compilato e l'altro no, restituisci errore
                    if (ssid_zone and not zone_entity_id) or (zone_entity_id and not ssid_zone):
                        if not ssid_zone:
                            errors["base"] = "ssid_missing"
                        if not zone_entity_id:
                            errors["base"] = "zone_missing"
                        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                    # Controlla il nome inserito per la rete
                    if len(ssid_zone.encode("utf-8")) > 32:
                        errors["base"] = "ssid_too_long"
                        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                    # Recupero SSID principale della configurazione base e le altre eventuali reti per le zone extra già salvate
                    home_ssid = self._base_data.get("home_wifi_ssid", "").strip()
                    existing_ssids = [home_ssid] + [
                        z["ssid"].strip()
                        for z in self._zones_to_edit
                        if not z.get("delete")
                    ]

                    # Evita di inserire un SSID già configurato (case-sensitive, come da standard Wi-Fi)
                    if ssid_zone in existing_ssids:
                        errors["base"] = "ssid_already_exists"
                        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                    # Recupero le zone esistenti di HA come entity_id
                    ha_zone_entity_ids = {state.entity_id for state in self.hass.states.async_all("zone")}
                    # Controllo che la zona selezionata sia valida
                    if zone_entity_id not in ha_zone_entity_ids:
                        errors["base"] = "invalid_zone"
                        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                    # Se entrambi i campi sono compilati correttamente, memorizza la rete
                    self._zones_to_edit.append({"ssid": ssid_zone, "zone": zone_entity_id})
                    if add_another:
                        self._current_index = len(self._zones_to_edit)
                        return await self.async_step_edit_zones()

                    # Non è stato selezionato il tasto aggiunti altra rete, salva tutto e termina
                    data = dict(self._base_data)
                    cleaned = [{"ssid": z["ssid"], "zone": z["zone"]} for z in self._zones_to_edit if not z.get("delete")]
                    data["extra_zones"] = cleaned
                    self.hass.config_entries.async_update_entry(self._entry, data=data)
                    await async_soft_reload_entry(self.hass, self._entry)
                    return self.async_create_entry(title="", data={})

                return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)


        # Altrimenti mostriamo una rete esistente dopo aver verificato che la relativa zona esista ancora
        current = self._zones_to_edit[self._current_index]
        zone_entity_id = current.get("zone", "")
        zone_state = self.hass.states.get(zone_entity_id)
        # Se la zona esiste ancora, usa il suo ID, altrimenti imposta il valore di default su "-"
        if zone_state:
            zone_default = zone_entity_id
        else:
            zone_default = "-"

        schema = vol.Schema(
            {
                vol.Required("ssid_zone", description={"translation_key": "ssid_zone"}, default=current.get("ssid", "")): str,
                vol.Required(
                    "zone_name",
                    description={"translation_key": "zone_name"},
                    default=zone_default,
                ): selector(
                    {
                        "select": {
                            "options": zone_options,
                            "mode": "dropdown",
                            "custom_value": False,
                        }
                    }
                ),
                vol.Optional("delete", description={"translation_key": "delete"}, default=False): bool,
            }
        )

        if user_input is not None:
            if user_input.get("delete"):
                self._zones_to_edit[self._current_index]["delete"] = True
            else:
                ssid_zone = (user_input.get("ssid_zone") or "").strip()
                zone_entity_id = (user_input.get("zone_name") or "").strip()
                
                # Se uno è compilato e l'altro no, restituisci errore
                if (ssid_zone and not zone_entity_id) or (zone_entity_id and not ssid_zone):
                    if not ssid_zone:
                        errors["base"] = "ssid_missing"
                    if not zone_entity_id:
                        errors["base"] = "zone_missing"
                    return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)
                    
                # Controlla il nome inserito per la rete
                if len(ssid_zone.encode("utf-8")) > 32:
                    errors["base"] = "ssid_too_long"
                    return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                # Recupero SSID principale della configurazione base e le altre eventuali reti per le zone extra già salvate
                home_ssid = self._base_data.get("home_wifi_ssid", "").strip()
                existing_ssids = [home_ssid] + [
                    z["ssid"].strip() for i, z in enumerate(self._zones_to_edit)
                    if i != self._current_index and not z.get("delete")
                ]

                # Evita di inserire un SSID già configurato (case-sensitive, come da standard Wi-Fi)
                if ssid_zone in existing_ssids:
                    errors["base"] = "ssid_already_exists"
                    return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                # Recupero le zone esistenti di HA come entity_id
                ha_zone_entity_ids = {state.entity_id for state in self.hass.states.async_all("zone")}
                # Controllo che la zona selezionata sia valida
                if zone_entity_id not in ha_zone_entity_ids:
                    errors["base"] = "invalid_zone"
                    return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)

                # Se entrambi i campi sono compilati correttamente, memorizza la rete
                self._zones_to_edit[self._current_index].update({"ssid": ssid_zone, "zone": zone_entity_id})

            self._current_index += 1
            return await self.async_step_edit_zones()

        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)
