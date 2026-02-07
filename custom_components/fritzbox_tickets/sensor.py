import requests
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
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
        return {"tickets": self._tickets}

    def update(self):
        url = f"{self._host}/data.lua?lang=de&page=kids_profile"
        r = requests.get(url, auth=(self._username, self._password), timeout=10)
        r.raise_for_status()

        data = r.json()
        self._tickets = [
            t["id"] for t in data.get("data", {}).get("tickets", [])
        ]
