# Light setup

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ELEMENTS, DEFAULT_COORDINATOR
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):

    full_elements = config_entry.options.get(CONF_ELEMENTS, [])
    
    entities = [
      OnOffLight(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") == "ON_OFF_LIGHT"
    ]
    
    async_add_entities(entities)


class OnOffLight(PLC_device, LightEntity):
    # Implementation of an on/off light.
    # https://developers.home-assistant.io/docs/core/entity/light/
    
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF
    

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]):
        self._id_suffix = device.get("u_state_addr", "unknown").replace(".", "_")
        self._availability_check = "u_state_value"
        super().__init__(coordinator, device)  # Handles name, unique_id, device_info    

    @property
    def is_on(self) -> bool | None:
        """Return if the light is on."""
        # This needs to enumerate to true or false
        value = self._device.get("u_state_value")
        if value is None:
            return False
        return bool(int(value))
    
    def _turn(self, target_state: str) -> int:
        
        if "change_type" not in self._device:
            _LOGGER.error(f"Action required for: {self._device["device_id"]} but no 'change_type' given")
            raise HomeAssistantError(f"'{self._device["device_id"]}' is misconfigured: missing 'change_type'")     
        
        if self._device["change_type"] == "tap": #send 1 if need to change
            if (self.is_on and target_state == "ON") or (not self.is_on and target_state == "OFF"):
                return -1
            else: 
                return 1 
        elif self._device["change_type"] == "value": #switch by sending value: 1 for ON and 0 for OFF
            if target_state == "ON": return 1
            elif target_state == "OFF" : return 0
            else:
                _LOGGER.debug("Action requested but unknown target state given")
                return -1
        else:
            _LOGGER.error("Action required but the device has unknown change_type value")
            raise HomeAssistantError(f"'{self._device["device_id"]}' is misconfigured: wrong 'change_type' value")    

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        value_to_write = self._turn("ON")
        if value_to_write > -1:
          await self._write("change_addr_plc", value_to_write)

        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        value_to_write = self._turn("OFF")
        if value_to_write > -1:
          await self._write("change_addr_plc", value_to_write)

        await self.coordinator.async_refresh()