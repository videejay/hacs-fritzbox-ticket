from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
):
    async_add_entities([FritzboxTicketsUpdateButton(hass, entry)])


class FritzboxTicketsUpdateButton(ButtonEntity):
    """
    Button to manually trigger FRITZ!Box ticket update
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self._hass = hass
        self._entry_id = entry.entry_id

    @property
    def name(self):
        return "Tickets aktualisieren"

    @property
    def unique_id(self):
        return "fritzbox_tickets_manual_update"

    @property
    def icon(self):
        return "mdi:refresh"

    async def async_press(self):
        """
        Trigger sensor update immediately
        """
        entity_id = "sensor.fritzbox_internet_tickets"

        await self._hass.services.async_call(
            "homeassistant",
            "update_entity",
            {"entity_id": entity_id},
            blocking=True,
        )
