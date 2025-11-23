# Binary sensor setup

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ELEMENTS, DEFAULT_COORDINATOR
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_TO_CLASS = {
    "MOVEMENT_SENSOR": BinarySensorDeviceClass.MOTION,
    "HEAT_SENSOR": BinarySensorDeviceClass.HEAT,
    "DOOR_SENSOR": BinarySensorDeviceClass.DOOR,
    "WINDOW_SENSOR": BinarySensorDeviceClass.WINDOW,
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    full_elements = config_entry.options.get(CONF_ELEMENTS, [])

    entities = [
      BinarySensor(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") in DEVICE_TYPE_TO_CLASS
    ]

    async_add_entities(entities)

class BinarySensor(PLC_device, BinarySensorEntity):
    # Implementation of a binary sensor.
    # https://developers.home-assistant.io/docs/core/entity/binary-sensor/

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        """Initialise entity."""
        super().__init__(coordinator, device)

        self._attr_device_class = DEVICE_TYPE_TO_CLASS.get(device.get("device_type"))

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self._device.get("u_data_value")
        if value is None:
            return None
        try:
            # Assuming '1' means on/detected, '0' means off/not detected
            return bool(int(value))
        except ValueError:
            _LOGGER.warning("Invalid binary sensor value: %s", value)
            return None