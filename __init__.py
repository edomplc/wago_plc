"""The Integration 101 Template integration.

This shows how to use the requests library to get and use data from an external device over http and
uses this data to create some binary sensors (of a generic type) and sensors (of multiple types).

Things you need to change
1. Change the api call in the coordinator async_update_data and the config flow validate input methods.
2. The constants in const.py that define the api data parameters to set sensors for (and the sensor async_setup_entry logic)
3. The specific sensor types to match your requirements.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.helpers.aiohttp_client import async_get_clientsession  

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_ELEMENTS, CONF_SETTINGS_GROUP_NAME, DEFAULT_SETTINGS_INTERVAL, CONF_SYM_FILE
from .coordinator import IntegrationCoordinator

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# A list of the different platforms we wish to setup.
# Add or remove from this list based on your specific need
# of entity platform types.
# ----------------------------------------------------------------------------
PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
    Platform.COVER, 
    Platform.SWITCH,
]

type MyConfigEntry = ConfigEntry[RuntimeData]


@dataclass
class RuntimeData:
    """Class to hold your data."""

    coordinators: dict[str, DataUpdateCoordinator] 
    cancel_update_listener: Callable


async def async_setup_entry(hass: HomeAssistant, config_entry: MyConfigEntry) -> bool:
    """Set up Example Integration from a config entry."""
    
    # Get a shared async session (pre-configured with HA's proxy, etc.)
    session = async_get_clientsession(hass)

    # ----------------------------------------------------------------------------
    # Initialise the coordinators that manages data updates from your api.
    # This is defined in coordinator.py
    # ----------------------------------------------------------------------------

    coordinators = {
        "live": IntegrationCoordinator(
            hass,
            config_entry, 
            session,
            "live", 
            config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        "hourly": IntegrationCoordinator(
            hass,
            config_entry, 
            session,
            "hourly",
            3600
        ),
        CONF_SETTINGS_GROUP_NAME: IntegrationCoordinator(
            hass, 
            config_entry,
            session,
            CONF_SETTINGS_GROUP_NAME,
            DEFAULT_SETTINGS_INTERVAL
        ),
    }

    # Initial refresh for all
    for coord in coordinators.values():
        await coord.async_config_entry_first_refresh()
        
        # commented out, because if there are no devices the coord.data = [] and it is fine...
        # if not coord.data:
        #    raise ConfigEntryNotReady(f"Failed initial data for {coord.group_name}")

    # ----------------------------------------------------------------------------
    # Initialise a listener for config flow options changes.
    # ----------------------------------------------------------------------------
    cancel_update_listener = config_entry.async_on_unload(
        config_entry.add_update_listener(_async_update_listener)
    )

    # ----------------------------------------------------------------------------
    # Add the coordinator and update listener to your config entry to make
    # accessible throughout your integration
    # ----------------------------------------------------------------------------
    config_entry.runtime_data = RuntimeData(coordinators, cancel_update_listener)

    # ----------------------------------------------------------------------------
    # Setup platforms (based on the list of entity types in PLATFORMS defined above)
    # This calls the async_setup method in each of your entity type files.
    # ----------------------------------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Return true to denote a successful setup.
    return True


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle config options update.

    Reload the integration when the options change.
    Called from our listener created above.
    """
    _LOGGER.debug("Options changed; reloading config entry %s", config_entry.entry_id)
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Delete device if selected from UI.

    Adding this function shows the delete device option in the UI.
    Remove this function if you do not want that option.
    You may need to do some checks here before allowing devices to be removed.
    """

    # Step 1: Extract device_id from identifiers (assuming format (DOMAIN, device_id))
    device_id = None
    for domain, identifier in device_entry.identifiers:
        if domain == DOMAIN:
            device_id = identifier
            break
    
    if not device_id:
        _LOGGER.warning("Deleted device has no matching identifier for domain %s; skipping cleanup", DOMAIN)
        return True  # Allow deletion anyway, as it might be a foreign device

    # Step 2: Get current elements list (default to empty list if missing)
    elements = config_entry.options.get(CONF_ELEMENTS, []).copy()  # Copy to avoid mutating original

    # Step 3: Filter out the element matching the device_id
    original_count = len(elements)
    elements = [elem for elem in elements if elem.get("device_id") != device_id]

    if len(elements) == original_count:
        _LOGGER.debug("No matching element found for device_id %s; no changes to elements", device_id)
    else:
        _LOGGER.debug("Removed element for device_id %s from config_entry.options", device_id)

    # Step 4: Update config_entry.options with the new elements list
    new_options = {**config_entry.options, CONF_ELEMENTS: elements}
    try:
        hass.config_entries.async_update_entry(config_entry, options=new_options)
    except Exception as e:
        raise HomeAssistantError(f"Failed to update config entry after device deletion: {e}") from e

    # Optional: Trigger a reload if you want immediate entity recreation (test carefully)
    # await hass.config_entries.async_reload(config_entry.entry_id)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: MyConfigEntry) -> bool:
    """Unload / Reload a config entry.

    This is called when you remove your integration or shutdown HA.
    If you have created any custom services, they need to be removed here too.
    """
  
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    
    # Unload services explicitly
    domain_services = hass.services.async_services_for_domain(DOMAIN)
    for service in domain_services:
        hass.services.async_remove(DOMAIN, service)
    
    # Optional: Clean up any other resources (e.g., if coordinator has custom shutdown)
    if hasattr(config_entry.runtime_data, 'coordinator'):
        # If your coordinator has an async_shutdown method, call it here
        # await config_entry.runtime_data.coordinator.async_shutdown()
        pass
    
    # Clear runtime data
    config_entry.runtime_data = None
    
    return unload_ok

async def async_remove_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle removal of a config entry."""
    _LOGGER.info("PLC config entry is being removed – cleaning up SYM file")

    sym_file = config_entry.options.get(CONF_SYM_FILE)  # or CONF_SYM_FILE
    if sym_file and os.path.exists(sym_file):
        try:
            await hass.async_add_executor_job(os.remove, sym_file)
            _LOGGER.info("Successfully deleted SYM file: %s", sym_file)
        except Exception as err:
            _LOGGER.error("Failed to delete SYM file %s: %s", sym_file, err)
    else:
        _LOGGER.debug("No SYM file found to clean up")
