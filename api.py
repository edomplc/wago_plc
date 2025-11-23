"""WAGO API 

Move it to PYPI.  Work in progress

"""

import random
import logging

import aiohttp  # import for async HTTP
import asyncio  # import for TimeoutError

import requests

_LOGGER = logging.getLogger(__name__)


class API:
    
    def __init__(self) -> None:
        """Initialise."""
        self._session = requests.Session()  # Reuse session for efficiency
        self._simulation_mode = False

    def connect(self) -> bool:
        """Connect to api."""
        return True
    def check_host(self) -> int:
        return True
           
    async def get_data(self, session: aiohttp.ClientSession, host: str, addrs: list[str]) -> list[str]:
        """Get API data from PLC by sending a POST request with address payload.

        Builds a pipe-separated payload from the provided addresses and parses
        the response into a list of values. Assumes response is '|val1|val2|...|'.

        Args:
            addrs: List of PLC address strings (e.g., ['2|112|1|0']).

        Returns:
            List of parsed values from the PLC response.

        Raises:
            ValueError: If input is invalid (e.g., non-list or non-string elements).
            APIConnectionError: On network/HTTP errors.
        """

        #_LOGGER.debug("addrs: %s", str(addrs))
        _LOGGER.debug("Reading data...")

        if not isinstance(addrs, list):
            raise ValueError("addrs must be a list of strings")

        # Filter valid addresses (optional: add regex validation if needed, e.g., r'^\d+(\|\d+)*$')
        valid_addrs = []
        for addr in addrs:
            if isinstance(addr, str) and addr:  # Non-empty string
                valid_addrs.append(addr)
            else:
                _LOGGER.warning("Skipping invalid address: %s (must be non-empty str)", addr)


        num_elements = len(valid_addrs)
        if num_elements == 0:
            _LOGGER.warning("No valid addresses provided; returning empty list")
            return []

        # handle simulation mode
        if self._simulation_mode:
            simulated_values = []
            for addr in valid_addrs:
                variable_type = int(addr.split('|')[-1])
                if variable_type == 0:
                    new_value = random.choice([0, 1])
                else:
                    new_value = random.randint(100, 299)
                simulated_values.append(str(new_value))

            _LOGGER.debug(f"Replying in simulation mode with values: {str(simulated_values)}")
            return simulated_values

        # Build the payload string: "|0|num|addr1|addr2|...|"
        payload_parts = [f"|0|{num_elements}"]
        for key, addr in enumerate(valid_addrs):  # enumerate gives zero-based index
            payload_parts.append(f"|{key}|{addr}")
        payload = "".join(payload_parts) + "|"
        #_LOGGER.debug("Built PLC query payload (length %d): %s", len(payload), payload)

        url = f"http://{host}/PLC/webvisu.htm"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        #_LOGGER.debug("Sending POST to URL: %s with headers %s", url, headers)

        try:
            async with session.post(url, data=payload, headers=headers, timeout=10) as response:  # Added headers
              response.raise_for_status()  # Raises ClientResponseError for 4xx/5xx

              if not (text := await response.text()):
                  _LOGGER.warning("Empty response from PLC; returning empty list")
                  return []
              
              #_LOGGER.debug("Raw reply: %s", text)
              # Parse to match PHP: Trim '|', split '|', convert to float (assuming numeric PLC values)
              result = text.strip('|')
              values = result.split('|')

              # Validate length (unchanged, but now with floats)
              if len(values) != num_elements:
                  _LOGGER.warning(
                      "Response value count (%d) does not match requested elements (%d): %s",
                      len(values), num_elements, values
                  )

              _LOGGER.debug("Parsed PLC reply: %s", values)
              return values

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout while connecting to PLC: %s", err)  # Optional: Add specific logging
            raise APIConnectionError(f"Connection timeout: {err}") from err
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Connection error to PLC: %s", err)  # Optional logging
            raise APIConnectionError(f"Connection error: {err}") from err
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("HTTP response error from PLC (status %d): %s", err.status, err)
            raise APIConnectionError(f"HTTP error (status {err.status}): {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("General aiohttp client error: %s", err)
            raise APIConnectionError(f"Request failed: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during PLC data fetch")
            raise APIConnectionError(f"Unexpected error: {err}") from err

    async def set_data(self, session: aiohttp.ClientSession, host: str, address: str, value: str) -> bool:
        """Set a value for a single PLC address via POST request.

        Sends a write request to the WAGO PLC with the specified address and value,
        formatted to match the PLC's expected protocol.

        Args:
            session: aiohttp ClientSession for async requests (passed from coordinator).
            address: PLC address string (e.g., '2|112|1|0' for .OUT1).
            value: Value to set (e.g., '0' or '1' for OFF/ON).

        Raises:
            ValueError: If address or value is invalid (not a non-empty string).
            APIConnectionError: On network/HTTP errors or if the PLC indicates failure.
        """
        _LOGGER.debug(f"Writting data to: {address} value {value}")
        if not isinstance(address, str) or not address:
            raise ValueError("Address must be a non-empty string")

        # Build payload: |1|1|0|address|value| (matches PHP's |1|1|0|ADR|VAL|)
        payload = f"|1|1|0|{address}|{value}|"
        #_LOGGER.debug("Built PLC write payload (length %d): %s", len(payload), payload)

        url = f"http://{host}/PLC/webvisu.htm"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        #_LOGGER.debug("Sending POST to URL: %s with headers %s", url, headers)

        try:
            async with session.post(url, data=payload, headers=headers, timeout=10) as response:
                response.raise_for_status()
                text = await response.text()
                _LOGGER.debug("Writting values; Raw reply: %s", text)

                # Check for success response (|0|)
                if text.strip() != "|0|":
                    _LOGGER.error("PLC write failed; unexpected response: %s", text)
                    raise APIConnectionError(f"PLC write failed with response: {text}")
                
                #_LOGGER.debug("PLC write successful for address %s with value %s", address, value)

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout while writing to PLC: %s", err)
            raise APIConnectionError(f"Connection timeout: {err}") from err
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Connection error while writing to PLC: %s", err)
            raise APIConnectionError(f"Connection error: {err}") from err
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("HTTP response error from PLC (status %d): %s", err.status, err)
            raise APIConnectionError(f"HTTP error (status {err.status}): {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("General aiohttp client error: %s", err)
            raise APIConnectionError(f"Request failed: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during PLC data write")
            raise APIConnectionError(f"Unexpected error: {err}") from err

        return True
    

class APIAuthError(Exception):
    """Exception class for auth error."""


class APIConnectionError(Exception):
    """Exception class for connection error."""
