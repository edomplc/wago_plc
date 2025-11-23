"""Switch setup for our Integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEFAULT_COORDINATOR, CONF_ELEMENTS
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    
    full_elements = config_entry.options.get(CONF_ELEMENTS, [])

    entities = [
      OnOffSwitch(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") == "SWITCH"
    ]
    async_add_entities(entities)
    

class OnOffSwitch(PLC_device, SwitchEntity):
    # Implementation of an on/off switch.
    # More at: https://developers.home-assistant.io/docs/core/entity/switch/

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        """Initialise entity."""

        super().__init__(coordinator, device)

    @property
    def is_on(self) -> bool | None:
        """Return if the switch is on."""
        # This needs to enumerate to true or false
        value = self._device.get("u_data_value")
        if value is None:
            return False
        return bool(int(value))
    
          
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._write("u_data_addr_plc", 1)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._write("u_data_addr_plc", 0)
        await self.coordinator.async_refresh()