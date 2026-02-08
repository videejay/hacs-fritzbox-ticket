import asyncio
import aiohttp
import hashlib
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime
import logging

from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

_LOGGER = logging.getLogger(__name__)

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
    _LOGGER.debug("SID login: requesting challenge from %s", host)

    async with session.get(f"{host}/login_sid.lua", timeout=REQUEST_TIMEOUT) as resp:
        xml = await resp.text()
        _LOGGER.debug("SID login: challenge response XML: %s", xml)
        root = ET.fromstring(xml)
        challenge = root.findtext("Challenge")

    if not challenge:
        raise Exception("No challenge from FRITZ!Box")

    response_hash = hashlib.md5(
        f"{challenge}-{password}".encode("utf-16le")
    ).hexdigest()
    response = f"{challenge}-{response_hash}"

    _LOGGER.debug("SID login: requesting SID")

    async with session.get(
        f"{host}/login_sid.lua",
        params={"username": username, "response": response},
        timeout=REQUEST_TIMEOUT,
    ) as resp:
        xml = await resp.text()
        _LOGGER.debug("SID login: SID response XML: %s", xml)
        root = ET.fromstring(xml)
        sid = root.findtext("SID")

    if not sid or sid == "0000000000000000":
        raise Exception("SID login failed")

    _LOGGER.debug("SID login successful, SID=%s", sid)
    return sid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    async_add_entities([FritzboxTicketsSensor(hass, entry.data)])


class FritzboxTicketsSensor(Entity):
    """
    FRITZ!Box Internet Tickets sensor (FHEM-compatible)
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
            _LOGGER.debug("Using cached SID %s", self._sid)
            return self._sid

        _LOGGER.debug("SID expired or missing, performing login")
        self._sid = await _login_sid(
            self._session,
            self._host,
            self._username,
            self._password,
        )
        self._sid_valid_until = now + SID_LIFETIME
        return self._sid

    async def _detect_luaquery_path(self, sid):
        _LOGGER.debug("Detecting luaQuery endpoint")

        for path in LUAQUERY_PATHS:
            try:
                _LOGGER.debug("Trying luaQuery path: %s", path)
                async with self._session.get(
                    f"{self._host}{path}",
                    params={
                        "sid": sid,
                        "query": "userticket:settings/ticket/list(id)",
                    },
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    _LOGGER.debug(
                        "luaQuery test %s returned HTTP %s",
                        path,
                        resp.status,
                    )
                    if resp.status == 200:
                        _LOGGER.debug("Using luaQuery endpoint: %s", path)
                        return path
            except Exception as err:
                _LOGGER.debug("luaQuery path %s failed: %s", path, err)

        raise Exception("No working luaQuery endpoint found")

    async def async_update(self):
        _LOGGER.debug("Starting ticket update")

        try:
            sid = await self._get_sid()

            if not self._luaquery_path:
                self._luaquery_path = await self._detect_luaquery_path(sid)

            url = f"{self._host}{self._luaquery_path}"
            params = {
                "sid": sid,
                "query": "userticket:settings/ticket/list(id)",
            }

            _LOGGER.debug("Requesting tickets from %s params=%s", url, params)

            async with self._session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                _LOGGER.debug("Ticket query HTTP status: %s", resp.status)
                resp.raise_for_status()
                data = await resp.json()

            _LOGGER.debug("Raw ticket query response: %s", data)

            tickets = []

            # FIX: FRITZ!Box returns {"query": [ ... ]}
            if isinstance(data, dict) and "query" in data:
                for entry in data["query"]:
                    if isinstance(entry, dict) and "id" in entry:
                        tickets.append(entry["id"])

            _LOGGER.debug("Parsed tickets: %s", tickets)
            self._tickets = tickets

        except asyncio.CancelledError:
            _LOGGER.debug("Update cancelled due to shutdown/reload")
            return

        except Exception as err:
            _LOGGER.error("Ticket update failed: %s", err, exc_info=True)
