import voluptuous as vol
import requests
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD

class FritzboxTicketsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                url = f"{user_input[CONF_HOST]}/data.lua?lang=de&page=kids_profile"
                r = requests.get(
                    url,
                    auth=(user_input[CONF_USERNAME], user_input[CONF_PASSWORD]),
                    timeout=10
                )
                r.raise_for_status()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="FRITZ!Box Internet Tickets",
                    data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="http://fritz.box"): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors
        )
