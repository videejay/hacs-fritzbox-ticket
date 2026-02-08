import asyncio
import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime

from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

# Polling interval
SCAN_INTERVAL = timedelta(minutes=5)

# SID validity
SID_LIFETIME = timedelta(minutes=9)

# Possible AVM luaQuery endpoints (FRITZ!OS dependent)
LUAQUERY_PATHS = [
    "/luaquery.lua",
    "/luaquery",
    "/query.lua",
    "/cgi-bin/luaquery.lua",
]


async def _login_sid(session, host, username, password):
    async with session.get(f"{host}/login_sid.lua", timeout=10) as resp:
        xml = await resp.text()
        root = ET.fromstring(xml)
        challenge = root.findtext("Challenge")

    if not challenge:
        raise Exception("No challenge from FRITZ!Box")

    response_hash = hashlib.md5(
        f"{challenge}-{password}".encode("utf-16le")
    ).hexdigest()
    response = f"{challenge}-{response_hash}"

    async with session.get(
        f"{host}/login_sid.lua",
        params={"username": username, "response": response},
        timeout=10,
    ) as resp:
        xml = await resp.text()
        root = ET.fromstring(xml)
        sid = root.findtext("SID")

    if not sid or sid == "0000000000000000":
        raise Exception("SID login failed")

    return sid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    async_add_entities([FritzboxTicketsSensor(entry.data)])


class FritzboxTicketsSensor(Entity):
    """
    FRITZ!Box Internet Tickets sensor
    (AVM luaQuery implementation)
    """

    def __init__(self, data):
        self._host = data[CONF_HOST]
        self._username = data[CONF_USERNAME]
        self._password = data[CONF_PASSWORD]

        self._tickets = []

        self._sid = None
        self._sid_valid_until = None

        self._luaquery_path = None  # autodetected

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

    async def _get_sid(self, session):
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

    async def _detect_luaquery_path(self, session, sid):
        """
        Detect working luaQuery endpoint (FRITZ!OS dependent)
        """
        for path in LUAQUERY_PATHS:
            try:
                async with session.get(
                    f"{self._host}{path}",
                    params={
                        "sid": sid,
                        "query": "userticket:settings/ticket/list(id)",
                    },
                    timeout=10,
                ) as resp:
                    if resp.status == 200:
                        return path
            except Exception:
                continue

        raise Exception("No working luaQuery endpoint found")

    async def async_update(self):
        try:
            async with aiohttp.ClientSession() as session:
                sid = await self._get_sid(session)

                if not self._luaquery_path:
                    self._luaquery_path = await self._detect_luaquery_path(
                        session, sid
                    )

                async with session.get(
                    f"{self._host}{self._luaquery_path}",
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

        except asyncio.CancelledError:
            # Home Assistant shutdown / restart
            return
