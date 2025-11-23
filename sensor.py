"""Sensor setup for our Integration."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature, LIGHT_LUX, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ELEMENTS, DEFAULT_COORDINATOR
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_TO_CLASS = {
    "TEMPERATURE_SENSOR": SensorDeviceClass.TEMPERATURE,
    "ILLUMINANCE_SENSOR": SensorDeviceClass.ILLUMINANCE,
    "POWER_METTER": SensorDeviceClass.POWER,
}

UNIT_TO_CLASS = {
    "Celcius": UnitOfTemperature.CELSIUS,
    "Lux": LIGHT_LUX,
    "Watt": UnitOfPower.WATT
}

DEVICE_TYPE_TO_DEFAULT_UNITS = {
    "TEMPERATURE_SENSOR": UnitOfTemperature.CELSIUS,
    "ILLUMINANCE_SENSOR": LIGHT_LUX,
    "POWER_METTER": UnitOfPower.WATT,
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the temperature sensors."""

    full_elements = config_entry.options.get(CONF_ELEMENTS, [])

    entities = [
      Sensor(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") in DEVICE_TYPE_TO_CLASS
    ]
    async_add_entities(entities)

class Sensor(PLC_device, SensorEntity):
    # Implementation of a sensor.
    # https://developers.home-assistant.io/docs/core/entity/sensor/

    _attr_state_class = SensorStateClass.MEASUREMENT  # Optional: For statistics like averages

    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        """Initialise entity."""
        super().__init__(coordinator, device)

        self._attr_device_class = DEVICE_TYPE_TO_CLASS.get(device.get("device_type"))
        unit_class = UNIT_TO_CLASS.get(device.get("unit", "none"), DEVICE_TYPE_TO_DEFAULT_UNITS.get(device.get("device_type")))

        self._attr_native_unit_of_measurement = unit_class
        self._divisor = device.get("divisor", 1)


    @property
    def native_value(self) -> float | None:
        """Return the value of the sensor."""
        value = self._device.get("u_data_value")
        if value is None:
            return None
        try:
            return float(value) / self._divisor
        except ValueError:
            _LOGGER.warning("Invalid sensor value: %s", value)
            return None
        