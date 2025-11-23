"""Cover setup for our Integration."""

import logging
from typing import Any
import asyncio

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_WRITE_DEBOUNCE, DEFAULT_WRITE_DEBOUNCE, CONF_ELEMENTS, DEFAULT_COORDINATOR
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

# Mapping from your config 'device_type' to HA CoverDeviceClass
# Add more as needed; fallback to None for generic
DEVICE_TYPE_TO_CLASS = {
    "AWNING": CoverDeviceClass.AWNING,
    "BLIND": CoverDeviceClass.BLIND,
    "CURTAIN": CoverDeviceClass.CURTAIN,
    "DAMPER": CoverDeviceClass.DAMPER,
    "DOOR": CoverDeviceClass.DOOR,
    "GARAGE": CoverDeviceClass.GARAGE,
    "GATE": CoverDeviceClass.GATE,
    "SHADE": CoverDeviceClass.SHADE,
    "SHUTTER": CoverDeviceClass.SHUTTER,
    "WINDOW": CoverDeviceClass.WINDOW,
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up cover entities from config entry."""

    full_elements = config_entry.options.get(CONF_ELEMENTS, [])

    entities = [
      Cover(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") in DEVICE_TYPE_TO_CLASS
    ]
    async_add_entities(entities)

class Cover(PLC_device, CoverEntity):
    # Implementation of a cover.
    # more at: https://developers.home-assistant.io/docs/core/entity/cover

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        self._id_suffix = device.get("u_position_addr", "unknown").replace(".", "_")
        self._availability_check = "u_position_value" #overwrite default attribute to check for availability
        super().__init__(coordinator, device)

        # Set device class based on config (this applies the class-specific behaviors)
        self._attr_device_class = DEVICE_TYPE_TO_CLASS.get(device.get("device_type"))

        # Define supported features (adjust based on your API capabilities)
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION  
        )

        # Write debounce
        self._write_debounce = coordinator.config_entry.options.get(CONF_WRITE_DEBOUNCE, DEFAULT_WRITE_DEBOUNCE)

    @property #overwrite property of the PLC_device
    def available(self) -> bool:
        return self.coordinator.last_update_success and "u_position_value" in self._device
    
    @property
    def current_cover_position(self) -> int | None:
        return 100*int(self._device.get("u_position_value"))/255
    
    @property
    def is_closed(self) -> bool | None:
        return self._device.get("u_position_value") == '0'
    
    @property
    def is_closing(self) -> bool | None:
        return self._device.get("u_is_closing_value") == '1'
    
    @property
    def is_opening(self) -> bool | None:
        return self._device.get("u_is_opening_value") == '1'

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""        
        await self._write("open_addr_plc", 1)

        self._device["u_is_opening_value"] = '1'
        _LOGGER.debug(f"Opening cover {self.name}, u_is_opening_value = {self._device.get("u_is_opening_value")}")
        await asyncio.sleep(self._write_debounce)
        await self.coordinator.async_request_refresh()  # Trigger poll to update state

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self._write("close_addr_plc", 1)
        self._device["u_is_closing_value"] = '1'
        _LOGGER.debug(f"Closing cover {self.name}")
        await asyncio.sleep(self._write_debounce)
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug(f"Stopping cover {self.name}, u_is_opening_value = {self._device.get("u_is_opening_value")}")
        if self._device.get("u_is_opening_value") == '1': 
            await self._write("close_addr_plc", 1)
        elif self._device.get("u_is_closing_value") == '1': 
            await self._write("open_addr_plc", 1)
        _LOGGER.debug(f"Stopping cover {self.name}")
        await asyncio.sleep(self._write_debounce)
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover shutter to a specific position."""
        target_position = int(255 * (kwargs["position"] / 100))
        await self._write("set_pos_addr_plc", target_position)
        await self._write("go_to_pos_addr_plc", 1)
        _LOGGER.debug(f"Setting cover {self.name} to position {target_position}")
        await asyncio.sleep(self._write_debounce)
        await self.coordinator.async_request_refresh()
