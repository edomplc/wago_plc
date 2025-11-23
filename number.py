# Number setup 

import logging
from typing import Any
import asyncio

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime, UnitOfLength, DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .const import CONF_WRITE_DEBOUNCE, CONF_ELEMENTS, DEFAULT_COORDINATOR
from .coordinator import IntegrationCoordinator

from .generic_device import PLC_device

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_TO_CLASS = {
    "TIME_SETTER": NumberDeviceClass.DURATION,
    "TEMPERATURE_SETTER": NumberDeviceClass.TEMPERATURE,
    "ANGLE_SETTER": NumberDeviceClass.WIND_DIRECTION,
    "DISTANCE_SETTER": NumberDeviceClass.DISTANCE,
    "GENERIC_SETTER": None
}
UNIT_TO_CLASS = {
    "hours": UnitOfTime.HOURS,
    "minutes": UnitOfTime.MINUTES,
    "seconds": UnitOfTime.SECONDS,
    "celcius": UnitOfTemperature.CELSIUS,
    "degree" : DEGREE,
    "none" : None,
    "meter" : UnitOfLength.METERS
}

DEVICE_TYPE_TO_DEFAULT_UNITS = {
    "TIME_SETTER": UnitOfTime.MINUTES,
    "TEMPERATURE_SETTER": UnitOfTemperature.CELSIUS,
    "ANGLE_SETTER": DEGREE,
    "DISTANCE_SETTER" : UnitOfLength.METERS
}

MODE_TO_CLASS = {
    "slider" : NumberMode.SLIDER,
    "box" : NumberMode.BOX,
    "auto" : NumberMode.AUTO,
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up number entities from config entry."""

    full_elements = config_entry.options.get(CONF_ELEMENTS, [])

    entities = [
      Number(
          config_entry.runtime_data.coordinators[elem.get("coordinator_name", DEFAULT_COORDINATOR)], 
          elem
      )
      for elem in full_elements
      if elem.get("device_type") in DEVICE_TYPE_TO_CLASS
    ]
    async_add_entities(entities)

class Number(PLC_device, NumberEntity):
    # Implementation of a temperature setpoint number entity.
    # https://developers.home-assistant.io/docs/core/entity/number
    
    def __init__(self, coordinator: IntegrationCoordinator, device: dict[str, Any]) -> None:
        """Initialise entity."""
        super().__init__(coordinator, device)

        self._attr_device_class = DEVICE_TYPE_TO_CLASS.get(device.get("device_type"))

        if self._attr_device_class == None:
            unit_class = device.get("unit", None) # allow custom units without refering to Default Unit classes
        else:
            unit_class = UNIT_TO_CLASS.get(device.get("unit", "err"), DEVICE_TYPE_TO_DEFAULT_UNITS.get(device.get("device_type")))

        self._attr_native_unit_of_measurement = unit_class
        self._divisor = device.get("divisor", 1)

        # Number-specific attributes
        if "min_value" in device:
            self._attr_native_min_value = device.get("min_value", 5.0)
        if "max_value" in device:
            self._attr_native_max_value = device.get("max_value", 25.0)
        self._attr_native_step = device.get("step", 0.5)
        self._attr_suggested_display_precision = device.get("precision", 0)
        self._attr_mode = MODE_TO_CLASS.get(device.get("mode"), "auto")

        # Device registry info (ensures separate devices per element)

        # Write debounce from config (like in cover.py)
        self._write_debounce = coordinator.config_entry.options.get(CONF_WRITE_DEBOUNCE, 0.1)

    @property
    def native_value(self) -> int | None:
        """Return the value of the sensor."""
        value = self._device.get("u_data_value")
        if value is None:
            return None
        try:
            return int(float(value) / self._divisor)
        except ValueError:
            _LOGGER.warning("Invalid sensor value: %s", value)
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new setpoint value and write to PLC."""
        # Update local state first (optimistic update)
        new_value = int(value * self._divisor)
        self._device["u_data_value"] = new_value

        # Write to PLC via your API 
        await self._write("u_data_addr_plc", new_value)

        _LOGGER.debug(f"Set {self.name} to {value}")

        # Debounce and refresh (like in cover.py)
        await asyncio.sleep(self._write_debounce)
        await self.coordinator.async_refresh()  # Immediate update to confirmvv