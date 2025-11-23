"""DataUpdateCoordinator for our integration."""

from datetime import timedelta
import logging
from typing import Any, List

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import DOMAIN, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import API, APIConnectionError
from .const import  CONF_ELEMENTS, DEFAULT_COORDINATOR



_LOGGER = logging.getLogger(__name__)


class IntegrationCoordinator(DataUpdateCoordinator[List[dict[str, Any]]]):

    data: list[dict[str, Any]]

    def __init__(
        self, 
        hass: HomeAssistant, 
        config_entry: ConfigEntry,       # for fetching the configuration data
        session: aiohttp.ClientSession,  # needed for the API to work in async
        group_name: str,                 # used to identify the coordinator
        update_interval: timedelta       # update interval in second
      ) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.host = config_entry.data[CONF_HOST]
        self.all_elements = config_entry.options.get(CONF_ELEMENTS, [])
        self.group_name = group_name     
        self.session = session            # Store the async session
        self.poll_interval = update_interval

        self.api = API()        

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id}) - {self.group_name}",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=self.poll_interval),
        )



    async def async_update_data(self):
        # get elements grouped by the coordinator_name.  If none configured, reach for the DEFAULT_COORDINATOR
        elements = [elem for elem in self.all_elements if elem.get("coordinator_name", DEFAULT_COORDINATOR) == self.group_name]
        #_LOGGER.debug("async_update_data elements of %s : %s", self.group_name, str(elements))

        if not elements:
            _LOGGER.debug(f"{self.group_name} coordinator - No elements configured; retriving nothing....")
            return self.all_elements        

        addrs = []
        mapping = []  # List of (element_name, sub_key) tuples, parallel to addrs
        data = {}  # Our return structure: {element_name: {sub_key: value, ...}}

        
        # Iterate over elements and collect 'u_....' attributes 

        for elem in elements:
            element_id = elem.get("device_id")

            data[element_id] = {}  # Initialize sub-dict for this element

            # Iterate over keys to find readable *_addr_plc

            #update_addresses = [key for key in element if (key.startswith("u_") and key.endswith("_addr_plc"))]
            #_LOGGER.debug("The 'udpate_addresses': %s", update_addresses)

            for key in list(elem.keys()):
                if key.startswith("u_") and key.endswith("_addr_plc"):
                    addrs.append(elem[key])

                    # Derive sub_key by stripping "_addr_plc"
                    value_key = key[:-len("_addr_plc")]+ "_value"
                    mapping.append((elem, value_key))
            
        #_LOGGER.debug("The 'mapping': %s", mapping)

        if not addrs:
            _LOGGER.warning(f"{self.group_name} coordinator - No update addresses found; returning empty data")
            return self.all_elements 
        
        #_LOGGER.debug("The 'udpate_addresses': %s", addrs)

        # Step 2: Call API (fixed to be async with session)
        try:
            api_data = await self.api.get_data(self.session, self.host, addrs)

            if len(api_data) != len(addrs):
                raise UpdateFailed(f"{self.group_name} coordinator - Response length mismatch: expected {len(addrs)}, got {len(api_data)}")

            # Step 3: Map values back to data structure
            for i, val in enumerate(api_data):
                #_LOGGER.debug("Assigning values from API': index: %i, value: %s", i, val)
                elem, value_key = mapping[i]
                #_LOGGER.debug("Updated element': device_id: %s, attribute: %s", elem.get("device_id"), value_key)
                elem[value_key] = val

        except APIConnectionError as err:
          _LOGGER.error(err)
          raise UpdateFailed(err) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        # What is returned here is stored in self.data by the DataUpdateCoordinator
        _LOGGER.debug(f"{self.group_name} coordinator - post update elements: %s", str(elements))
        return self.all_elements 
        

    # ----------------------------------------------------------------------------
    # Here we add some custom functions on our data coordinator to be called
    # from entity platforms to get access to the specific data they want.
    #
    # These will be specific to your api or yo may not need them at all
    # ----------------------------------------------------------------------------
    def get_device(self, device_id: int) -> dict[str, Any]: # IS IT USED?
        """Get a device entity from our api data."""
        try:
            return [
                devices for devices in self.data if devices["device_id"] == device_id
            ][0]
        except (TypeError, IndexError):
            # In this case if the device id does not exist you will get an IndexError.
            # If api did not return any data, you will get TypeError.
            return None

    def get_device_parameter(self, device_id: int, parameter: str) -> Any:
        """Get the parameter value of one of our devices from our api data."""
        if device := self.get_device(device_id):
            return device.get(parameter)
