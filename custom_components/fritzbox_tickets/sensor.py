import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

SCAN_INTERVAL = 300  # 5 Minuten


async def _get_sid(host, username, password):
    async with aiohttp.ClientSession() as session:
        # 1. Challenge holen
        async with session.get(f"{host}/login_sid.lua") as resp:
            xml = await resp.text()
            root = ET.fromstring(xml)
            challenge = root.findtext("Challenge")

        # 2. Response berechnen
        response_str = f"{challenge}-{password}"
        response_hash = hashlib.md5(
            response_str.encode("utf-16le")
        ).hexdigest()
        response = f"{challenge}-{response_hash}"

        # 3. SID holen
        params = {
            "username": username,
            "response": response
        }
        async with session.get(
            f"{host}/login_sid.lua", params=params
        ) as resp:
            xml = await resp.text()
            root = ET.fromstring(xml)
            sid = root.findtext("SID")

        if sid == "0000000000000000":
            raise Exception("SID login failed")

        return sid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities
):
    async_add_entities([FritzboxTicketsSensor(entry.data)])


class FritzboxTicketsSensor(Entity):
    def __init__(self, data):
        self._host = data[CONF_HOST]
        self._username = data[CONF_USERNAME]
        self._password = data[CONF_PASSWORD]
        self._tickets = []

    @property
    def name(self):
        return "FRITZ!Box Internet Tickets"

    @property
    def unique_id(self):
        return "fritzbox_internet_tickets"

    @property
    def state(self):
        return len(self._tickets)

    @property
    def extra_state_attributes(self):
        return {
            "tickets": self._tickets
        }

    async def async_update(self):
        sid = await _get_sid(
            self._host,
            self._username,
            self._password
        )

        url = f"{self._host}/data.lua"
        params = {
            "sid": sid,
            "lang": "de",
            "page": "kids_profile"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

        self._tickets = [
            t["id"]
            for t in data.get("data", {}).get("tickets", [])
            if "id" in t
        ]
