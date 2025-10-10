"""Config flow for Wi-Fi Sensor Tracker."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import selector
from homeassistant.helpers import entity_registry as er
from . import DOMAIN, async_soft_reload_entry


class WifiSensorTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wi-Fi Sensor Tracker."""

    VERSION = 1

    async def _get_wifi_sensors(self):
        """Return list of sensor entities matching Wi-Fi connection patterns."""
        entity_reg = er.async_get(self.hass)
        all_entities = [e.entity_id for e in entity_reg.entities.values() if e.entity_id.startswith("sensor.")]
        wifi_sensors = [
            eid for eid in all_entities
            if "_wifi_connection" in eid or "_ssid" in eid
        ]
        return sorted(wifi_sensors)

    async def async_step_import(self, import_config: dict):
        """Import from configuration.yaml."""
        return await self.async_step_user(user_input=import_config)

    async def async_step_user(self, user_input=None):
        """UI step for initial setup."""
        errors = {}

        wifi_sensors = await self._get_wifi_sensors()

        if not wifi_sensors:
            errors["sensors"] = "Nessun sensore Wi-Fi rilevato"

        schema = vol.Schema(
            {
                vol.Required("home_wifi_ssid"): str,
                vol.Required("sensors"): selector(
                    {
                        "entity": {
                            "multiple": True,
                            "include_entities": wifi_sensors,
                        }
                    }
                ),
                vol.Optional("consider_home", default=180): int,
            }
        )

        if user_input is not None:
            sensors = user_input.get("sensors", [])
            if not sensors:
                errors["sensors"] = "Seleziona almeno un sensore"
                return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

            return self.async_create_entry(title="Wi-Fi Sensor Tracker", data=user_input)

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return WifiSensorTrackerOptionsFlowHandler(config_entry)


class WifiSensorTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options updates for Wi-Fi Sensor Tracker."""

    def __init__(self, entry: config_entries.ConfigEntry):
        """Initialize the options flow with the existing entry."""
        self._entry = entry

    async def _get_wifi_sensors(self):
        """Return list of sensor entities matching Wi-Fi connection patterns."""
        entity_reg = er.async_get(self.hass)
        all_entities = [e.entity_id for e in entity_reg.entities.values() if e.entity_id.startswith("sensor.")]
        wifi_sensors = [
            eid for eid in all_entities
            if "_wifi_connection" in eid or "_ssid" in eid
        ]
        return sorted(wifi_sensors)

    async def async_step_init(self, user_input=None):
        """Manage options."""
        errors = {}

        wifi_sensors = await self._get_wifi_sensors()

        schema = vol.Schema(
            {
                vol.Required(
                    "home_wifi_ssid",
                    default=self._entry.data.get("home_wifi_ssid"),
                ): str,
                vol.Required(
                    "sensors",
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
                    default=self._entry.data.get("consider_home", 180),
                ): int,
            }
        )

        if user_input is not None:
            new_ssid = user_input.get("home_wifi_ssid")
            new_sensors = set(user_input.get("sensors", []))
            new_consider_home = user_input.get("consider_home", 180)

            old_ssid = self._entry.data.get("home_wifi_ssid")
            old_sensors = set(self._entry.data.get("sensors", []))
            old_consider_home = self._entry.data.get("consider_home", 180)

            if not new_sensors:
                errors["sensors"] = "Seleziona almeno un sensore"
                return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

            # 1. Calcola differenze
            sensors_to_add = new_sensors - old_sensors
            sensors_to_remove = old_sensors - new_sensors
            ssid_changed = new_ssid != old_ssid
            consider_home_changed = new_consider_home != old_consider_home

            # 2. Aggiorna il config entry
            self.hass.config_entries.async_update_entry(self._entry, data=user_input)

            # 3. Rimuove solo le entità dei sensori tolti
            if sensors_to_remove:
                entity_registry = er.async_get(self.hass)
                for sensor in sensors_to_remove:
                    entity_id = f"device_tracker.{sensor.replace('sensor.', '').replace('.', '_').replace('_connection', '')}"
                    entry = entity_registry.async_get(entity_id)
                    if entry:
                        entity_registry.async_remove(entry.entity_id)

            # 4. Se sono stati aggiunti nuovi sensori o cambiato l'SSID/consider_home, ricarica le piattaforme
            if sensors_to_add or sensors_to_remove or ssid_changed or consider_home_changed:
                await async_soft_reload_entry(self.hass, self._entry)

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
