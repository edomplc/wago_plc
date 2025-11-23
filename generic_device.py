# Base entity for all PLC devices

import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IntegrationCoordinator

_LOGGER = logging.getLogger(__name__)


class PLC_device(CoordinatorEntity):
    """Base class for all WAGO PLC entities."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device = device  # Raw dict from YAML + resolved _plc addresses

        # if entity_name defined, reach for it first
        # entity_name is created in config_flow while adding setting devices, which inherit device_name
        # from the main device
        self._attr_name = device.get("entity_name", device.get("device_name", "Unknown Device"))

        # check for non-default values
        if not hasattr(self, "_id_suffix"):
            self._id_suffix = device.get("u_data_addr", "unknown").replace(".", "_")
        if not hasattr(self, "_availability_check"):
            self._availability_check = "u_data_value"            

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{device.get('device_id')}_{self._id_suffix}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.get("device_id"))},
            name=device.get("device_name", "Unnamed Device"),
            model=device.get("device_type", "Generic"),
        )



    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._availability_check in self._device
    
    async def _write(self, plc_key: str, value: Any) -> None:
        """Write a value to the PLC using a resolved _plc address."""
        if plc_key not in self._device:
            _LOGGER.error("Device %s misconfigured: missing PLC address key '%s'", self._device.get("device_id"), plc_key)
            raise HomeAssistantError(f"Device '{self._device.get('device_id')}' missing PLC address for {plc_key}")
        await self.coordinator.api.set_data(self.coordinator.session, self.coordinator.host, self._device[plc_key], value)
