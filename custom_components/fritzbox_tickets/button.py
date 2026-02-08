from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    async_add_entities([FritzboxTicketsUpdateButton(hass, entry)])


class FritzboxTicketsUpdateButton(ButtonEntity):
    """
    Button to manually trigger update of all sensors
    belonging to this integration.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self._hass = hass
        self._entry_id = entry.entry_id

    @property
    def name(self):
        return "Tickets aktualisieren"

    @property
    def unique_id(self):
        return f"{self._entry_id}_manual_update"

    @property
    def icon(self):
        return "mdi:refresh"

    async def async_press(self):
        """
        Trigger update for all entities of this config entry
        """
        registry = er.async_get(self._hass)

        entity_ids = [
            entry.entity_id
            for entry in registry.entities.values()
            if entry.config_entry_id == self._entry_id
            and entry.domain == "sensor"
        ]

        if not entity_ids:
            return

        await self._hass.services.async_call(
            "homeassistant",
            "update_entity",
            {"entity_id": entity_ids},
            blocking=True,
        )
