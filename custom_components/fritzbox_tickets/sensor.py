import asyncio
import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime

from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

# Polling interval
SCAN_INTERVAL = timedelta(minutes=5)

# SID validity
SID_LIFETIME = timedelta(minutes=9)

# Possible AVM luaQuery endpoints
LUAQUERY_PATHS = (
    "/luaquery.lua",
    "/luaquery",
    "/query.lua",
    "/cgi-bin/luaquery.lua",
)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def _login_sid(session, host, username, password):
    async with session.get(f"{host}/login_sid.lua", timeout=REQUEST_TIMEOUT) as resp:
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
        timeout=REQUEST_TIMEOUT,
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
    async_add_entities([FritzboxTicketsSensor(hass, entry.data)])


class FritzboxTicketsSensor(Entity):
    """
    FRITZ!Box Internet Tickets sensor
    (HA-watchdog safe)
    """

    def __init__(self, hass: HomeAssistant, data):
        self._hass = hass
        self._host = data[CONF_HOST]
        self._username = data[CONF_USERNAME]
        self._password = data[CONF_PASSWORD]

        self._tickets = []

        self._sid = None
        self._sid_valid_until = None
        self._luaquery_path = None

        # Shared HA aiohttp session
        self._session = async_get_clientsession(hass)

    @property
    def name(self):
        return "Tickets"

    @property
    def unique_id(self):
        return "fritzbox_internet_tickets"

    @property
    def state(self):
        return len(self._tickets)

    @property
    def extra_state_attributes(self):
        return {"tickets": self._tickets}

    async def _get_sid(self):
        now = datetime.utcnow()

        if (
            self._sid
            and self._sid_valid_until
            and now < self._sid_valid_until
        ):
            return self._sid

        self._sid = await _login_sid(
            self._session,
            self._host,
            self._username,
            self._password,
        )
        self._sid_valid_until = now + SID_LIFETIME
        return self._sid

    async def _detect_luaquery_path(self, sid):
        for path in LUAQUERY_PATHS:
            try:
                async with self._session.get(
                    f"{self._host}{path}",
                    params={
                        "sid": sid,
                        "query": "userticket:settings/ticket/list(id)",
                    },
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status == 200:
                        return path
            except Exception:
                continue

        raise Exception("No working luaQuery endpoint found")

    async def async_update(self):
        try:
            sid = await self._get_sid()

            if not self._luaquery_path:
                # Detect once, cache forever
                self._luaquery_path = await self._detect_luaquery_path(sid)

            async with self._session.get(
                f"{self._host}{self._luaquery_path}",
                params={
                    "sid": sid,
                    "query": "userticket:settings/ticket/list(id)",
                },
                timeout=REQUEST_TIMEOUT,
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
            # Shutdown / reload
            return
