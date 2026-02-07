import voluptuous as vol
import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD


async def _test_sid_login(host, username, password):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{host}/login_sid.lua") as resp:
            xml = await resp.text()
            root = ET.fromstring(xml)
            challenge = root.findtext("Challenge")

        response = hashlib.md5(
            f"{challenge}-{password}".encode("utf-16le")
        ).hexdigest()
        response = f"{challenge}-{response}"

        async with session.get(
            f"{host}/login_sid.lua",
            params={"username": username, "response": response}
        ) as resp:
            xml = await resp.text()
            root = ET.fromstring(xml)
            sid = root.findtext("SID")

        if sid == "0000000000000000":
            raise Exception("Login failed")


class FritzboxTicketsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                await _test_sid_login(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD]
                )
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
