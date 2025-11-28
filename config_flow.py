"""Config flows for our integration.

This config flow demonstrates many aspects of possible config flows.

Multi step flows
Menus
Using your api data in your flow
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

#import base64  # Add this for base64 decoding

from homeassistant.const import (
    CONF_HOST,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    FlowResult, 
)

import homeassistant.helpers.device_registry as dr

# TODO - validate which imports are necessary!

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL, CONF_SYM_FILE, CONF_ELEMENTS, CONF_ELEMENTS_ACTION_MODE, CONF_SETTINGS_GROUP_NAME
#from .const import DEFAULT_WRITE_DEBOUNCE, CONF_WRITE_DEBOUNCE

#imports for file uploads
import aiofiles
import os
import uuid

import xml.etree.ElementTree as ET  #  for XML parsing

import yaml #for elements handling

# for testing PLC availability
import aiohttp
import asyncio

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Adjust the data schema to the data that you need
# ----------------------------------------------------------------------------
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, description={"suggested_value": "192.168.10.3"}): str, 
    }
)

# ----------------------------------------------------------------------------
# Example selectors
# There are lots of selectors available for you to use, described at
# https://www.home-assistant.io/docs/blueprint/selectors/
# ----------------------------------------------------------------------------


async def validate_host_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    # check if the host is available

    host = data[CONF_HOST]
    url = f"http://{host}/PLC/webvisu.htm" 
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=5) as response:
                if response.status != 200:
                    _LOGGER.error(f"Unexpected status: {response.status}")
                    raise CannotConnect(f"Unexpected status: {response.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error(f"Connection error to {host}: {err}")
            raise CannotConnect(f"Cannot connect to host: {err}") from err
        except Exception as err:  # Catch-all for unexpected issues
            _LOGGER.exception("Unexpected error during host validation")
            raise CannotConnect("Unexpected error during validation") from err
    
    return host

class ExampleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Integration."""

    VERSION = 1
    _input_data: dict[str, Any]
    _title: str

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:

        return OptionsFlowHandler()

    async def async_step_user(  # this is the name of the first step even if it does not concern the user :)
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.
        Called when you initiate adding an integration via the UI
        """

        errors: dict[str, str] = {}

        if user_input is not None:
            # The form has been filled in and submitted, so process the data provided.
            try:
                host = await validate_host_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            # so far there is NO authorization check with the PLC in webvisu provided by Codesys V2.3.
            # except InvalidAuth:
            #    errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if "base" not in errors:
                # Validation was successful, so proceed to the next step.
                title = "WAGO PLC Integration - "  + host
                # ----------------------------------------------------------------------------
                # Setting our unique id here just because we have the info at this stage to do that
                # and it will abort early on in the process if alreay setup.
                # You can put this in any step however.
                # ----------------------------------------------------------------------------
                await self.async_set_unique_id(title)
                self._abort_if_unique_id_configured()

                # Set our title variable here for use later
                self._title = title

                self._input_data = user_input

                # Finish up
                return self.async_create_entry(title=self._title, data=self._input_data)
                
                # IF there was a 2nd step of the initial config, this would be used
                #return await self.async_step_sym_file()

        # Show initial form.
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            last_step=True,  # Adding last_step True/False decides whether form shows Next or Submit buttons
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to reconfigure a config entry.

        This methid displays a reconfigure option in the integration and is
        different to options.
        It can be used to reconfigure any of the data submitted when first installed.
        This is optional and can be removed if you do not want to allow reconfiguration.
        """
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if user_input is not None:
            try:
                await validate_host_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
              return self.async_update_reload_and_abort(
                  config_entry,
                  unique_id=config_entry.unique_id,
                  data={**config_entry.data, **user_input},
                  reason="reconfigure_successful",
              )
            
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=config_entry.data[CONF_HOST]): str
                }
            ),
            errors=errors,
        )

# Options Flow manages setting the options of the integration
# which are availabe after adding the integration

class OptionsFlowHandler(OptionsFlow):

    def __init__(self) -> None:
        """Initialize options flow."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        # Decide what to show as the Options menu
        # Also need to be in strings.json and translation files.      
        # Base options (always shown)
        menu_options = ["refresh", "sym_file"]
        
        # Conditionally add "elements" if sym_file is defined
        # Check self.config_entry.data (or .options if stored there)
        if CONF_SYM_FILE in self.config_entry.options and self.config_entry.options[CONF_SYM_FILE]:
            menu_options.append("elements")
        
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )
    
    # Function checking if addresses provided by the user are in the sym_file and returning webvisu address form
    #
    # So if addr would be for example "PLC_PRG.Control_B_1PP2.T_UP"
    #
    # xml_vars would be a dictionary build of symbol file generated by codesys with a definition for example
    # "<Var Type="4" Flags="1073741825" Access="98" RefId="3" Offset="5644" TopLevelType="57">PLC_PRG.Control_B_1PP2.T_UP</Var>"
    #
    # xml_types is a dictionary build of type definitions from the symbol file, for example: 
    # "<TypeSimple TypeId="4" Size="4">TIME</TypeSimple>"
    #
    # and as a result, the function returns an addressed to be used in communication with the PLC via webvisu:
    # RefId=3, Offset=5644, size=4, type=7 (size and type from the DATA_TYPES, as defined by "TIME")
    # "3|5644|4|7"

    async def _check_addr_in_xml(
        self,
        addr: str,
        xml_vars: dict[str, dict[str, str]],
        xml_types: dict[str, str],
        ) -> dict[str, Any]:

        # --------------------------------------------------------------------
        # Mapping of PLC data types → visu_type / visu_size
        # --------------------------------------------------------------------
        DATA_TYPES = {
            "BOOL": {"visu_type": 0, "visu_size": 1},
            "INT": {"visu_type": 1, "visu_size": 2},
            "WORD": {"visu_type": 1, "visu_size": 2},
            "BYTE": {"visu_type": 2, "visu_size": 1},
            "DINT": {"visu_type": 4, "visu_size": 4},
            "DWORD": {"visu_type": 5, "visu_size": 4},
            "REAL": {"visu_type" : 6, "visu_size": 4},
            "TIME": {"visu_type": 7, "visu_size": 4},
            "SINT": {"visu_type": 14, "visu_size": 1},
            "USINT": {"visu_type": 15, "visu_size": 1},
            "UINT": {"visu_type": 16, "visu_size": 2},
            "UDINT": {"visu_type": 17, "visu_size": 4},
            "DT": {"visu_type": 20, "visu_size": 4},
        }

        if addr not in xml_vars:
            #_LOGGER.debug(f"xml_vars: {str(xml_vars)}")
            return {"error" : f"Address '{addr}' not found in symbol file."}
        
        attrib = xml_vars[addr] #copy attributes of variable found in SYM_XML
        var_type = attrib.get('Type') #for example 102

        if var_type not in xml_types:
            return {"error" : f"Var type '{var_type}' not defined in symbol file."}
        
        var_type_name = xml_types[var_type] #for example Bool
        _LOGGER.debug(f"Found variable type: {var_type_name}")
        
        if var_type_name not in DATA_TYPES:
            return {"error" :  f"Var type '{var_type_name}' for not defined in data conversion table."}
        
        visu_type = DATA_TYPES[var_type_name].get("visu_type")

        if var_type_name == "BOOL":
            if attrib.get('RefId') in ['1', '2']:
                visu_size = 0
            else:
                visu_size = 1
        else: 
            visu_size = DATA_TYPES[var_type_name].get("visu_size")

        _LOGGER.debug(f"Visu_type: {visu_type}")
        _LOGGER.debug(f"Visu_size: {visu_size}")

        return {"addr" : f"{attrib.get('RefId', '')}|{attrib.get('Offset', '')}|{visu_size}|{visu_type}"}
    
    async def _async_remove_existing_devices(self) -> None:
        """Remove all existing devices and their entities tied to this config entry."""
        device_registry = dr.async_get(self.hass)

        _LOGGER.debug(f"Clearing all devices for config entry {self.config_entry.entry_id}")
        device_registry.async_clear_config_entry(self.config_entry.entry_id)
    
    # function used by the async_step_elements
    # convert setting_... attributes into separate entities  
    async def _async_create_entities_for_blinds(self, data) -> None:
        
        SETTING_ENTITIES = {
            "time_up" :     {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "seconds", "divisor" : 1000, "max_value" : 180, "min_value" : 0, "step" : 1},
            "time_dn" :     {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "seconds", "divisor" : 1000, "max_value" : 180, "min_value" : 0, "step" : 1},
            "time_power" :  {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "seconds", "divisor" : 1000, "max_value" : 180, "min_value" : 0, "step" : 1},
            "shade_start_angle" : {"device_type" : "ANGLE_SETTER", "mode" : "box", "unit" : "degree", "min_value" : 0, "max_value" : 360, "step" : 5},
            "shade_end_angle" : {"device_type" : "ANGLE_SETTER", "mode" : "box", "unit" : "degree", "min_value" : 0, "max_value" : 360, "step" : 5},
            "shade_position" : {"device_type" : "GENERIC_SETTER", "mode" : "box", "unit" : "p", "min_value" : 0, "max_value" : 255, "step" : 5},
            "shade_delay"    : {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "seconds", "max_value" : 3600, "divisor" : 1000, "step" : 1},
        }

        for element in data:
            device_type = element.get("device_type", "unknown")
            if device_type == "BLIND":
                setting_keys = [key for key in element if key.startswith("setting_")]
                
                for setting_key in setting_keys: # setting_key example: "setting_time_up_addr" : PLC_PRG.Control_B_1PL2.T_UP
                    new_entity = await self._create_setting_entity(element, setting_key, SETTING_ENTITIES)
                    if new_entity:
                        data.append(new_entity)
                        
    # function used by the async_step_elements
    # convert setting_... attributes into separate entities  
    async def _async_create_entities_for_lights(self, data) -> None:
        
        # those are the accepted setting_ attributes with definition of what to make out of them
        SETTING_ENTITIES = {
            "auto_off_delay" :     {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "minutes",  "max_value" : 720, "min_value" : 0, "step" : 1},
            "auto_off_after_move_delay" :     {"device_type" : "TIME_SETTER", "mode" : "box", "unit" : "minutes",  "max_value" : 720, "min_value" : 0, "step" : 1},
            "auto_off" :  {"device_type" : "SWITCH"},
            "auto_on" : {"device_type" : "SWITCH"},
        }

        for element in data:
            device_type = element.get("device_type", "unknown")
            if device_type == "ON_OFF_LIGHT":
                setting_keys = [key for key in element if key.startswith("setting_")]
                
                for setting_key in setting_keys: # setting_key example: "setting_time_up_addr" : PLC_PRG.Control_B_1PL2.T_UP
                    new_entity = await self._create_setting_entity(element, setting_key, SETTING_ENTITIES)
                    if new_entity:
                        data.append(new_entity)
                                                
    # shortcut function used during creation of etities out of attributes
    async def _create_setting_entity(self, parent_element, setting_key, SETTING_ENTITIES) -> dict[str, Any]:
        
        OPTIONAL_SETTINGS = ["mode", "unit", "min_value", "max_value", "step", "divisor"]
        
        key = setting_key.removesuffix("_addr").removeprefix("setting_") # example "setting_time_up_addr" -> "time_up"
        if key in SETTING_ENTITIES:
            setting_entity = SETTING_ENTITIES[key]
            new_entity = {
                "device_name" : parent_element.get("device_name"), # the same as the BLIND name not to overwritte the BLIND name
                "device_id" : parent_element.get("device_id"), # the same as the BLIND name to compose it into one device
                "entity_name" : key.replace("_", " ").title(), # specfic name for the entity used in DeviceInfo
                "u_data_addr" : parent_element.get(setting_key), # the address initially assigned to the attribute, which triggered creation of this entity
                "device_type" : setting_entity.get("device_type"),
                "coordinator_name" : CONF_SETTINGS_GROUP_NAME  
            }
            for optional_setting in OPTIONAL_SETTINGS:
                if optional_setting in setting_entity:
                    new_entity[optional_setting] = setting_entity.get(optional_setting)
            return new_entity
        else:
            return False
    
    # OPTION - set the refresh interval = how often to ask the PLC for fresh
    # data in case of the "live" coordinator
    async def async_step_refresh(self, user_input=None) -> FlowResult:
        """Handle menu refresh flow."""
        if user_input is not None:
            options = self.config_entry.options | user_input
            return self.async_create_entry(data=options)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): (vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL))),
            }
        )

        return self.async_show_form(step_id="refresh", data_schema=data_schema)
    
    # OPTION - set the time of delay between writting data to the PLC and
    # requesting a reload of values from the PLC. In some cases the old value 
    # gets returned before the requested new value is written 
    """
    async def async_step_write_debounce(self, user_input=None) -> FlowResult:
        if user_input is not None:
            options = self.config_entry.options | user_input
            return self.async_create_entry(data=options)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WRITE_DEBOUNCE,
                    default=self.config_entry.options.get(CONF_WRITE_DEBOUNCE, DEFAULT_WRITE_DEBOUNCE),
                ): (vol.All(vol.Coerce(int), vol.Clamp(min=0))),
            }
        )

        return self.async_show_form(step_id="refresh", data_schema=data_schema)
    """
    
    # OPTION - add the symbol XML file copied from the project directory and 
    # generated by Codesys.  This is the basis of converting variable names to 
    # specific addressess used for communication with the PLC
    async def async_step_sym_file(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the sym_file upload option."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Process the uploaded file
            #file_data = user_input["sym_file"]
            file_data = user_input.get("sym_file")

            if not isinstance(file_data, str):  # Check if str 
                errors["base"] = "invalid_file"  
            elif not file_data.strip(): # Check if non-empty
                errors["base"] = "empty_string"   
            elif len(file_data.encode('utf-8')) > 2_000_000:  # Limit to 2MB
                errors["base"] = "file_too_large"

            # Parse XML
            try:
                root = ET.fromstring(file_data)
                # Structural validation
                if root.tag != "CoDeSysSymbolTable":
                    errors["base"] = "CoDeSysSymbolTable_missing"
                elif root.find("SymbolVarList") is None:
                    errors["base"] = "SymbolVarList_missing"
                else:
                    # Optional: Check at least one <Var> with required attributes
                    var_elements = root.findall("SymbolVarList/Var")
                    if not var_elements:
                        errors["base"] = "Var_missing"
            except ET.ParseError as e:
                _LOGGER.error(f"XML parsing failed: {e}")
                errors["base"] = "xml_parser_error"


            if not errors:
                _LOGGER.debug("Sym_file input: size=%d, first_10=%s", len(file_data), file_data[:10])
                filename = f"{uuid.uuid4().hex}.xml"
                temp_dir = self.hass.config.path("custom_components", "wago_plc", "temp")
                file_path = os.path.join(temp_dir, filename)

                # Create dir if not exists (sync op, so use executor)
                await self.hass.async_add_executor_job(
                    lambda: os.makedirs(temp_dir, exist_ok=True)
                )

                # Write the string as UTF-8 bytes to file
                try:
                    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:  # "w" for text mode
                        await f.write(file_data)
                except Exception as e:
                    _LOGGER.error(f"Failed to write sym_file: {e}")
                    errors["base"] = "write_failed"
                else:
                    # Delete old file if exists
                    old_file = self.config_entry.options.get(CONF_SYM_FILE)
                    if old_file and os.path.exists(old_file):
                        await self.hass.async_add_executor_job(os.remove, old_file)
                    
                    # Update config_entry.data with the new file path
                    new_data = {**self.config_entry.options, CONF_SYM_FILE: file_path}
                    self.hass.config_entries.async_update_entry(self.config_entry, options=new_data)

                    # THIS IS USED ONLY WHEN THE SYM FILE IS RELOADED 
                    # Update the addresses of existing devices (if any are configured)
                    current_elements: list[dict] = self.config_entry.options.get(CONF_ELEMENTS, [])
                    
                    if current_elements:
                        _LOGGER.info("SYM file updated, re-mapping %d existing elements", len(current_elements))

                        var_types = root.findall("SymbolTypeList/TypeSimple") #all variable types used in SYM_XML
                        xml_types = {var.attrib["TypeId"]: var.text for var in var_types if var.text} # [0 : "BOOL", 3 : "BYTE...

                        var_elements = root.findall("SymbolVarList/Var") #all variables in SYM_XML
                        xml_vars = {var.text: var.attrib for var in var_elements if var.text}

                        error_count = 0
                        error_elements = ''
                        for element in current_elements:
                            addr_keys = [k for k in element.keys() if k.endswith("_addr")]
                            for addr_key in addr_keys:
                                addr = element[addr_key]
                                addr_check = await self._check_addr_in_xml(addr, xml_vars, xml_types)
                              
                                if "error" in addr_check:
                                    error_elements += (f"Device - {element.get("device_id", "Unknown")}: " + addr_check["error"] + "\n\n")
                                    error_count += 1
                                    if addr_key + "_plc" in element:
                                      # this will delete addreses for both read and write actions
                                      # -> deleted read addresses will not be used by coordinators in refresh rounds => safe
                                      # -> deleted write addresses pose a risk for device-related actions => must be validated at device level
                                      del element[addr_key + "_plc"]
                                else:
                                    element[addr_key + "_plc"] = addr_check["addr"] # refresh the PLC address

                        # NOTE: We mutate config_entry.options in-place via reference.
                        # No async_update_entry() needed — changes are immediately effective.

                        #elements = {**self.config_entry.options, CONF_ELEMENTS: current_elements}
                        #self.hass.config_entries.async_update_entry(self.config_entry, options=elements)
                        if error_count:
                          _LOGGER.error(f"Encountered {error_count} errors while re-mapping elements to new SYM file:\n {error_elements}")
                          

                    # If no existing elements yet - just proceed normally
                    else:
                        _LOGGER.info("SYM file uploaded successfully. No existing elements to re-map.")
                    
                    
                    return self.async_create_entry(data=new_data)
        
        # Show the form on initial load (when user_input is None) - This was missing or indented wrong
        return self.async_show_form(
            step_id="sym_file",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYM_FILE): selector(
                        {"text": {"multiline": True, "type": "text"}}
                    ),
                }
            ),
            errors=errors,
        )
    
    # OPTION - add the YMAL data to define the devices
    # can be used as an increment - adding new ones or as a complete rewrite
    async def async_step_elements(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        
        """Handle elements configuration flow."""
        # We are adding elements by copying into a textfield a YAML structured list of elements

        errors: dict[str, str] = {}
        
        if not self.config_entry:
            _LOGGER.error("No config entry found for elements step")
            return self.async_abort(reason="no_config_entry")

        if user_input is not None:
            # Extract toggle value (default True for overwrite)
            action_mode = user_input[CONF_ELEMENTS_ACTION_MODE]          
            
            elements_yaml = user_input.get(CONF_ELEMENTS)

            # Initial validation of the input package
            if not isinstance(elements_yaml, str):
                errors["base"] = "not_a_string"
            elif not elements_yaml.strip():
                errors["base"] = "empty_string"
            elif len(elements_yaml.encode('utf-8')) > 2_000_000:  # 2MB limit
                errors["base"] = "input_too_large"

            # Parse and validate YAML
            if not errors:
                try:
                    data = yaml.safe_load(elements_yaml)

                    if not isinstance(data, list):
                        errors["base"] = "elements_not_list"
                    else:
                        for element in data:
                            if not isinstance(element, dict):
                                errors["base"] = "invalid_element_structure"
                                break
                            element_id = element.get("device_id", "Unknown element")  # Safe access for dynamic errors

                            if not "device_id" in element:
                                errors["base"] = f"Device_id of one of the elements is missing"
                                break
                            
                            if not "device_type" in element:
                                errors["base"] = f"Attribute device_type for {element_id} is missing"
                                break

                except yaml.YAMLError as e:
                    _LOGGER.error(f"YAML parsing failed: {e}")
                    errors["base"] = "invalid_yaml"
            
                
            #  For various devices, their attributes should be used to create new entities of the same device.
            if not errors:
                await self._async_create_entities_for_blinds(data)
                await self._async_create_entities_for_lights(data)

            # Now check, if:
            # -- the provided element has an u_* address (at least one to update values)
            # -- the the provided addressess (like .OUT1 or PLC_PRG.XYZ) are found in the provided SYM file data)
            
            if not CONF_SYM_FILE in self.config_entry.options:
                errors["base"] = "SYM file not available... It is impossible to assign PLC addresses"
                
            if not errors:
                try:
                    sym_file_path = self.config_entry.options[CONF_SYM_FILE]
                    async with aiofiles.open(sym_file_path, "r", encoding="iso-8859-1") as f:
                        xml_content = await f.read()
                    try:
                        root = ET.fromstring(xml_content)
                        var_types = root.findall("SymbolTypeList/TypeSimple") #all variable types used in SYM_XML
                        xml_types = {var.attrib["TypeId"]: var.text for var in var_types if var.text} # [0 : "BOOL", 3 : "BYTE...
                        #_LOGGER.debug("xml-vars: %s", str(xml_types))

                        var_elements = root.findall("SymbolVarList/Var") #all variables in SYM_XML
                        xml_vars = {var.text: var.attrib for var in var_elements if var.text}
                        
                        #example <Var Type="102" Flags="33554464" Access="98" RefId="2" Offset="112">.OUT1</Var>

                        for element in data:
                            element_id = element.get("device_id", "Unknown")

                            # 1) Check if element has at least 1 attribute starting with "u_"
                            has_u_attr = any((key.startswith("u_") and key.endswith("_addr")) for key in element)
                            if not has_u_attr:
                                errors["base"] = f"Element '{element_id}' must have at least one 'u_XXXX_addr' attribute"
                                break
                            # 2) Check all attributes of the element ending with "_addr"
                            addr_keys = [key for key in element if key.endswith("_addr")]

                            for addr_key in addr_keys:
                                addr = element[addr_key]
                                
                                addr_check = await self._check_addr_in_xml(addr, xml_vars, xml_types)
                                
                                if "error" in addr_check:
                                    errors["base"] = f"Variable: {element_id}: " + addr_check["error"]
                                    break  # Break inner loop on error
                                
                                element[addr_key + "_plc"] = addr_check["addr"] # assign the PLC address to a new attribute
                    except:
                        errors["base"] = "XML parsing error"
                            
                except (OSError, ET.ParseError) as e:
                    _LOGGER.error(f"Failed to validate against sym_file: {e}")
                    errors["base"] = "sym_file_validation_failed"

            if not errors:
                _LOGGER.debug("Parsed elements: %s", str(data))

                if action_mode == "replace":
                    new_elements = data  # Replace fully
                    await self._async_remove_existing_devices()
                elif action_mode == "add":
                    existing_elements = self.config_entry.options.get(CONF_ELEMENTS, [])
                    new_elements = existing_elements + data  # Append (duplicates already caught above)
                else:
                    errors["base"] = "invalid_action_mode"

                if not errors:

                  # Store in options
                  elements = {**self.config_entry.options, CONF_ELEMENTS: new_elements}
                  self.hass.config_entries.async_update_entry(self.config_entry, options=elements)
                  return self.async_create_entry(data = elements)
            
        return self.async_show_form(
            step_id="elements",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ELEMENTS_ACTION_MODE, default="add"): selector({
                        "select": {
                            "options": [
                                {"label": "Add to existing devices", "value": "add"},
                                {"label": "Replace all devices (deletes existing)", "value": "replace"},
                            ],
                            "mode": "dropdown",  # Or "list" for radio-like
                        }
                    }),
                    vol.Required(CONF_ELEMENTS): selector(
                        {"text": {"multiline": True, "type": "text"}}
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "instructions": (
                    "Enter a YAML list of PLC elements, e.g.:\n"
                    "  - device_name: Bedroom Light\n"
                    "    device_id: Light_1\n"
                    "    device_type: ON_OFF_LIGHT\n"
                    "    u_state_addr: .OUT1\n"
                    "    change_addr: PLC_PRG.VIS1\n"
                    "    change_type: tap\n"
                    "# Ensure names match variables in the uploaded symbol file."
                )
            }
        )

# NOTE - fill it with functions or... remove

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
