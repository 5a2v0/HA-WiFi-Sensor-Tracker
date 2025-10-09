"""Config flow for Wi-Fi Sensor Tracker."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import selector
from . import DOMAIN


class WifiSensorTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wi-Fi Sensor Tracker."""

    VERSION = 1

    async def async_step_import(self, import_config: dict):
        """Import from configuration.yaml."""
        return await self.async_step_user(user_input=import_config)

    async def async_step_user(self, user_input=None):
        """UI step for initial setup."""
        errors = {}

        schema = vol.Schema(
            {
                vol.Required("home_wifi_ssid"): str,
                vol.Required("sensors"): selector(
                    {
                        "entity": {
                            "domain": "sensor",
                            "multiple": True,
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

    async def async_step_init(self, user_input=None):
        """Manage options."""
        errors = {}

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
                            "domain": "sensor",
                            "multiple": True,
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
            sensors = user_input.get("sensors", [])
            if not sensors:
                errors["sensors"] = "Seleziona almeno un sensore"
                return self.async_show_form(
                    step_id="init", data_schema=schema, errors=errors
                )

            #Aggiorna il config entry e ricarica l'integrazione
            self.hass.config_entries.async_update_entry(self._entry, data=user_input)
            await self.hass.config_entries.async_reload(self._entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
