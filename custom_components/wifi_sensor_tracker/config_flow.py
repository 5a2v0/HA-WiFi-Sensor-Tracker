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


class WifiSensorTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisci il config flow for Wi-Fi Sensor Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        """Inizializza il flow"""
        self._base_config: Dict[str, Any] = {}
        self._extra_zones: List[Dict[str, str]] = []


    async def _get_wifi_sensors(self) -> List[str]:
        """Restituisci la lista di sensori filtrati in base al nome"""
        entity_reg = er.async_get(self.hass)
        all_entities = [e.entity_id for e in entity_reg.entities.values() if e.entity_id.startswith("sensor.")]
        wifi_sensors = [
            eid for eid in all_entities
            if "_wifi_connection" in eid or "_ssid" in eid or "_wi_fi_connection" in eid
        ]
        return sorted(wifi_sensors)


    async def _get_zone_options(self):
        """Restituisci una lista delle zone esistenti"""
        zones = []
        for state in self.hass.states.async_all("zone"):
            name = state.attributes.get("friendly_name", state.entity_id.split(".", 1)[-1])
            zones.append(name)
        unique = sorted(list(dict.fromkeys(zones)))
        return [{"value": z, "label": z} for z in unique]


    async def async_step_import(self, import_config: dict) -> Dict[str, Any]:
        """Importa da eventuale configuration.yaml."""
        return await self.async_step_user(user_input=import_config)


    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Initial step: home SSID, sensors, consider_home, optional add_zone checkbox."""
        errors: Dict[str, str] = {}

        wifi_sensors = await self._get_wifi_sensors()

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

        zone_options = await self._get_zone_options()
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
            zone_name = (user_input.get("zone_name") or "").strip()
            add_another = user_input.get("add_another", False)

            # Schermata nuova rete, nessun ssid e zona inseriti, salva tutto e chiudi
            if not ssid_zone and not zone_name:
                data = dict(self._base_config)
                data["extra_zones"] = list(self._extra_zones)
                return self.async_create_entry(title="Wi-Fi Sensor Tracker", data=data)

            # Se uno è compilato e l'altro no, restituisci errore
            if (not ssid_zone and zone_name) or (ssid_zone and not zone_name):
                if not ssid_zone:
                    errors["base"] = "ssid_missing"
                elif not zone_name:
                    errors["base"] = "zone_missing"
                return self.async_show_form(step_id="add_zones", data_schema=schema, errors=errors)

            # Controlla il nome inserito per la rete
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
            self._extra_zones.append({"ssid": ssid_zone, "zone": zone_name})

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


    async def _get_wifi_sensors(self) -> List[str]:
        entity_reg = er.async_get(self.hass)
        all_entities = [e.entity_id for e in entity_reg.entities.values() if e.entity_id.startswith("sensor.")]
        wifi_sensors = [
            eid for eid in all_entities
            if "_wifi_connection" in eid or "_ssid" in eid or "_wi_fi_connection" in eid
        ]
        return sorted(wifi_sensors)


    async def _get_zone_options(self):
        zones = []
        for state in self.hass.states.async_all("zone"):
            name = state.attributes.get("friendly_name", state.entity_id.split(".", 1)[-1])
            zones.append(name)
        unique = sorted(list(dict.fromkeys(zones)))
        return [{"value": z, "label": z} for z in unique]


    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Step principale di modifica base."""
        errors: Dict[str, str] = {}

        wifi_sensors = await self._get_wifi_sensors()

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
                    default="\n".join(
                        f"SSID: {z.get('ssid', '?')} → Zona: {z.get('zone', '?')}"
                        for z in self._zones_to_edit if not z.get("delete")
                    ) or "Nessuna rete/zone aggiuntiva",
                ): selector(
                    {
                        "text": {
                            "multiline": True,
                        }
                    }
                ),
                #vol.Optional("manage_zones", default=False): bool,
                vol.Optional(
                    "zone_action",
                    #default="none",
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
            #manage_zones = user_input.get("manage_zones", False)
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
        zone_options = await self._get_zone_options()
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
                    zone_name = (user_input.get("zone_name") or "").strip()
                    add_another = user_input.get("add_another", False)

                    if not ssid_zone and not zone_name:
                        # Schermata nuova rete, nessuna nuova rete ed ssid inseriti, salva tutto e chiudi
                        data = dict(self._base_data)
                        cleaned = [{"ssid": z["ssid"], "zone": z["zone"]} for z in self._zones_to_edit if not z.get("delete")]
                        data["extra_zones"] = cleaned
                        self.hass.config_entries.async_update_entry(self._entry, data=data)
                        await async_soft_reload_entry(self.hass, self._entry)
                        return self.async_create_entry(title="", data={})

                    # Se uno è compilato e l'altro no, restituisci errore
                    if (ssid_zone and not zone_name) or (zone_name and not ssid_zone):
                        if not ssid_zone:
                            errors["base"] = "ssid_missing"
                        if not zone_name:
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

                    # Se entrambi i campi sono compilati correttamente, memorizza la rete
                    self._zones_to_edit.append({"ssid": ssid_zone, "zone": zone_name})
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


        # Altrimenti mostriamo una rete esistente
        current = self._zones_to_edit[self._current_index]
        schema = vol.Schema(
            {
                vol.Required("ssid_zone", description={"translation_key": "ssid_zone"}, default=current.get("ssid", "")): str,
                vol.Required(
                    "zone_name",
                    description={"translation_key": "zone_name"},
                    default=current.get("zone", ""),
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
                zone_name = (user_input.get("zone_name") or "").strip()
                
                # Se uno è compilato e l'altro no, restituisci errore
                if (ssid_zone and not zone_name) or (zone_name and not ssid_zone):
                    if not ssid_zone:
                        errors["base"] = "ssid_missing"
                    if not zone_name:
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
    
                # Se entrambi i campi sono compilati correttamente, memorizza la rete
                self._zones_to_edit[self._current_index].update({"ssid": ssid_zone, "zone": zone_name})

            self._current_index += 1
            return await self.async_step_edit_zones()

        return self.async_show_form(step_id="edit_zones", data_schema=schema, errors=errors)
