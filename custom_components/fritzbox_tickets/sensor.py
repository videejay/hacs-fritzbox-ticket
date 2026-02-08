import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime

from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

# Home Assistant polling interval
SCAN_INTERVAL = timedelta(minutes=5)

# FRITZ!Box SID validity (renew a bit earlier)
SID_LIFETIME = timedelta(minutes=9)


async def _login_sid(session, host, username, password):
    """
    Perform AVM challenge-response login and return SID
    """
    # Step 1: get challenge
    async with session.get(f"{host}/login_sid.lua") as resp:
        xml = await resp.text()
        root = ET.fromstring(xml)
        challenge = root.findtext("Challenge")

    # Step 2: calculate response
    response_hash = hashlib.md5(
        f"{challenge}-{password}".encode("utf-16le")
    ).hexdigest()
    response = f"{challenge}-{response_hash}"

    # Step 3: request SID
    async with session.get(
        f"{host}/login_sid.lua",
        params={
            "username": username,
            "response": response,
        },
    ) as resp:
        xml = await resp.text()
        root = ET.fromstring(xml)
        sid = root.findtext("SID")

    if not sid or sid == "0000000000000000":
        raise Exception("FRITZ!Box SID login failed")

    return sid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    async_add_entities([FritzboxTicketsSensor(entry.data)])


class FritzboxTicketsSensor(Entity):
    """
    Sensor that exposes FRITZ!Box internet tickets
    using AVM luaQuery (FHEM-compatible).
    """

    def __init__(self, data):
        self._host = data[CONF_HOST]
        self._username = data[CONF_USERNAME]
        self._password = data[CONF_PASSWORD]

        self._tickets = []

        self._sid = None
        self._sid_valid_until = None

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

    async def _get_sid(self, session):
        """
        Return cached SID or perform login if expired
        """
        now = datetime.utcnow()

        if (
            self._sid
            and self._sid_valid_until
            and now < self._sid_valid_until
        ):
            return self._sid

        self._sid = await _login_sid(
            session,
            self._host,
            self._username,
            self._password,
        )
        self._sid_valid_until = now + SID_LIFETIME

        return self._sid

    async def async_update(self):
        """
        Fetch ticket list via AVM luaQuery
        """
        async with aiohttp.ClientSession() as session:
            sid = await self._get_sid(session)

            async with session.get(
                f"{self._host}/luaquery.lua",
                params={
                    "sid": sid,
                    "query": "userticket:settings/ticket/list(id)",
                },
                timeout=10,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        tickets = []
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and "id" in entry:
                    tickets.append(entry["id"])

        self._tickets = tickets
