import time
import random
import asyncio
from typing import Any, Set, Dict, List, Tuple, Optional

import httpx

from config import MAX_PROXY_RETRIES
from utils.logger import logger

# Default timeout for API requests
DEFAULT_TIMEOUT = 10  # seconds
PROXY_TIMEOUT = 5  # shorter timeout for proxy requests
PROXY_TEST_URL = "https://api.coingecko.com/api/v3/ping"  # URL to test proxy connection
RETRY_DELAY = 1  # seconds to wait between retries
MAX_RETRIES = 2  # maximum number of retry attempts


class ApiWorker:
    """Worker class for handling API requests with consistent error handling and proxy support."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize the API worker with configurable timeout."""
        # Initialize async client for asyncio support
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        self.proxy_list: List[str] = []
        self.valid_proxies: List[str] = []
        self.failed_proxies: Set[str] = set()  # Track proxies that have already failed
        self.proxy_last_used: Dict[str, float] = {}
        self.consecutive_proxy_failures = 0  # Track consecutive proxy failures
        self.last_proxy_success = time.time()  # Track last successful proxy use
        logger.debug(f"Initialized async API worker with timeout of {timeout} seconds")

    async def close(self):
        """Close the httpx client."""
        await self.client.aclose()
        logger.debug("Closed API worker client")

    def set_proxies(self, proxies: List[str]):
        """Set the list of available proxies."""
        self.proxy_list = proxies
        # Reset proxy tracking when setting new ones
        self.valid_proxies = []
        self.failed_proxies = set()
        self.proxy_last_used = {proxy: 0 for proxy in proxies}
        logger.info(f"Added {len(proxies)} proxies to rotation pool")

    def _format_proxy_for_httpx(self, proxy_url: str) -> str:
        """Format a proxy URL correctly for httpx client.

        Just return the URL as is, as httpx expects a simple string.
        """
        return proxy_url

    async def validate_proxy(self, proxy: str) -> bool:
        """Test if a proxy is working properly."""
        # Skip validation if we know it already failed
        if proxy in self.failed_proxies:
            logger.warning(f"Skipping known failed proxy: {proxy}")
            return False

        try:
            # Create a client with this specific proxy and a shorter timeout
            async with httpx.AsyncClient(
                proxy=proxy, timeout=PROXY_TIMEOUT, follow_redirects=True
            ) as test_client:
                response = await test_client.get(PROXY_TEST_URL)
                if response.status_code == 200:
                    return True

                # If we get a non-200 response, mark as failed
                logger.warning(
                    f"Proxy {proxy} returned status code {response.status_code}"
                )
                self.failed_proxies.add(proxy)
                return False
        except Exception as e:
            logger.warning(f"Proxy validation failed for {proxy}: {str(e)}")
            # Add to failed list so we don't try again
            self.failed_proxies.add(proxy)
            return False

    async def get_valid_proxy(self) -> Optional[str]:
        """Get a working proxy from the list, validating if necessary."""
        # If we have no proxies, return None
        if not self.proxy_list:
            return None

        # If we have valid proxies, return one at random
        if self.valid_proxies:
            proxy = random.choice(self.valid_proxies)
            # Record usage time to allow rotation
            self.proxy_last_used[proxy] = time.time()
            return proxy

        # Otherwise, validate proxies until we find a working one
        # Filter out known failed proxies
        untested_proxies = [p for p in self.proxy_list if p not in self.failed_proxies]
        if not untested_proxies:
            logger.error(
                "No untested proxies available - all proxies have failed validation"
            )
            return None

        random.shuffle(untested_proxies)  # Randomize order for better distribution

        for proxy in untested_proxies[:5]:  # Only try up to 5 untested proxies
            if await self.validate_proxy(proxy):
                self.valid_proxies.append(proxy)
                self.proxy_last_used[proxy] = time.time()
                logger.info(f"Found valid proxy: {proxy}")
                return proxy

        logger.error("No valid proxies found in the proxy list")
        return None

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_proxy: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Make a request to the API with retries and optional proxy support.
        Returns a tuple of (data, error). If successful, error will be None.
        If failed, data will be None and error will be a string error message.
        """
        # Track whether any proxy was successful
        any_proxy_succeeded = False
        tried_proxies = set()

        # Define base retry behavior
        MAX_RETRIES = 2
        RETRY_DELAY = 1  # seconds

        # First, try without a proxy (unless proxy required)
        if not use_proxy:
            for retry in range(MAX_RETRIES + 1):
                try:
                    response, error = await self._make_request(url)
                    if response:
                        return response, None
                    elif "rate limit" in error.lower() or "429" in error:
                        # We're rate limited, note it and potentially try with proxies
                        logger.warning(
                            f"Rate limited at {url}. Attempt {retry + 1}/{MAX_RETRIES + 1}"
                        )
                        if retry < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (retry + 1))
                            continue
                        break  # If we've exhausted retries, move on to proxies if available
                    else:
                        # Some other error occurred
                        return None, error
                except Exception as e:
                    logger.error(f"Unexpected error in API request: {e}")
                    if retry < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY * (retry + 1))
                        continue
                    return None, f"Error: {str(e)}"

        # If we're rate limited or requested to use proxy, try with proxies
        if use_proxy:
            # First check if we have proxy list configured
            if not self.proxy_list:
                logger.error(f"Rate limited at {url} but no proxies configured")
                return None, "RATE_LIMITED: No proxies configured"

            # Try multiple proxies if available
            tried_proxies = set()

            # If we have no valid proxies yet, try to validate some first
            if not self.valid_proxies and self.proxy_list:
                # Only try proxies that haven't failed before
                untested_proxies = [
                    p for p in self.proxy_list if p not in self.failed_proxies
                ]
                if untested_proxies:
                    logger.warning(
                        f"Trying to validate proxies for rate-limited request. Have {len(untested_proxies)} untested proxies."
                    )
                    for proxy in untested_proxies[
                        :5
                    ]:  # Try validating first 5 untested proxies
                        if await self.validate_proxy(proxy):
                            self.valid_proxies.append(proxy)
                            logger.warning(
                                f"Validated proxy {proxy} for use with rate-limited requests"
                            )

            # Now try with any valid proxies we have
            max_proxy_attempts = min(len(self.valid_proxies), MAX_PROXY_RETRIES)

            # Log clear information about proxy status
            logger.warning(
                f"Trying with proxies for rate-limited URL {url}. We have {len(self.valid_proxies)} valid proxies."
            )

            for proxy_attempt in range(max_proxy_attempts):
                proxy = await self.get_valid_proxy()

                if not proxy:
                    logger.error(
                        f"No valid proxy available for attempt {proxy_attempt + 1}"
                    )
                    # If we can't get a proxy, break out of the loop
                    break

                if proxy in tried_proxies:
                    logger.warning(f"Already tried proxy {proxy}, skipping")
                    continue

                tried_proxies.add(proxy)
                logger.warning(f"Attempting with proxy {proxy} for {url}")

                for retry in range(MAX_RETRIES + 1):
                    try:
                        response, error = await self._make_request(url, True, proxy)

                        if response:
                            logger.warning(f"Successful request with proxy {proxy}")
                            any_proxy_succeeded = True
                            return response, None
                        elif error and "rate limit" in error.lower():
                            logger.warning(
                                f"Rate limited with proxy {proxy} at {url}. Attempt {retry + 1}/{MAX_RETRIES + 1}"
                            )
                            # If we have retries left, wait and try again with same proxy
                            if retry < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY * (retry + 1))
                                continue
                            # Otherwise try another proxy
                            break
                        else:
                            logger.warning(f"Proxy API request failed: {error}")
                            # Try another proxy
                            break
                    except Exception as e:
                        # Remove from valid proxies on error
                        if proxy in self.valid_proxies:
                            self.valid_proxies.remove(proxy)
                            # Add to failed proxies
                            self.failed_proxies.add(proxy)
                        logger.error(
                            f"Proxy request error with {proxy} for {url}: {str(e)}"
                        )
                        break  # Try another proxy

            # After trying all available proxies, check if we need an early refresh
            if not tried_proxies:
                logger.error("RATE_LIMITED: No valid proxies were available to try")
                self.consecutive_proxy_failures += 1
                return None, "RATE_LIMITED: No valid proxies available"
            else:
                # Check if all proxies we tried failed
                all_failed = len(tried_proxies) > 0 and not any_proxy_succeeded
                if all_failed:
                    self.consecutive_proxy_failures += 1
                    current_time = time.time()
                    # If we haven't had a successful proxy use in 10 minutes and have multiple failures
                    if (
                        current_time - self.last_proxy_success > 600
                        and self.consecutive_proxy_failures >= 3
                    ):
                        logger.error(
                            "Multiple consecutive proxy failures detected, proxies may need refreshing"
                        )
                else:
                    # Reset failure counter if at least one proxy worked
                    self.consecutive_proxy_failures = 0

                logger.error(
                    f"RATE_LIMITED: All {len(tried_proxies)} attempted proxies failed or were rate limited"
                )
                return (
                    None,
                    f"RATE_LIMITED: All {len(tried_proxies)} attempted proxies failed or were rate limited",
                )

        # If we got here, it means we're either rate limited with no proxies allowed or proxies failed
        error_msg = "RATE_LIMITED: Rate limit exceeded"
        if use_proxy:
            error_msg += " and proxy attempts failed"
        logger.error(f"Request failed for {url}: {error_msg}")
        return None, error_msg

    async def _make_request(
        self, url: str, use_proxy: bool = False, proxy: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Make a request to the given URL, optionally using a proxy."""
        if use_proxy and not proxy and not self.valid_proxies:
            logger.error("Proxy requested but no valid proxies available")
            return None, "No valid proxies available"

        client = self.client
        proxy_used = None
        proxy_dict = None

        try:
            if use_proxy:
                if proxy:
                    # Use the specific proxy if provided
                    proxy_used = proxy
                    proxy_dict = self._format_proxy_for_httpx(proxy_used)
                elif self.valid_proxies:
                    # Otherwise use a random valid proxy
                    proxy_used = random.choice(self.valid_proxies)
                    proxy_dict = self._format_proxy_for_httpx(proxy_used)
                    logger.debug(f"Using proxy: {proxy_used}")

                # Create a new client with the proxy
                client = httpx.AsyncClient(timeout=self.timeout, proxy=proxy_dict)

            response = await client.get(url)
            response.raise_for_status()

            # Mark successful proxy use
            if proxy_used:
                self.last_proxy_success = time.time()
                # Reset consecutive failures on success
                self.consecutive_proxy_failures = 0

            return response.json(), None
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error: {e.response.status_code}"
            logger.error(f"{error_msg} for {url}")
            return None, error_msg
        except httpx.TimeoutException:
            if proxy_used:
                logger.error(f"Timeout with proxy {proxy_used} for {url}")
                self.failed_proxies.add(proxy_used)
            else:
                logger.error(f"Request timed out for {url}")
            return None, "Timeout"
        except httpx.RequestError as e:
            if proxy_used:
                logger.error(f"Request error with proxy {proxy_used} for {url}: {e}")
                self.failed_proxies.add(proxy_used)
            else:
                logger.error(f"Request error for {url}: {e}")
            return None, f"Request error: {e}"
        except Exception as e:
            if proxy_used:
                logger.error(f"Error with proxy {proxy_used} for {url}: {e}")
                self.failed_proxies.add(proxy_used)
            else:
                logger.error(f"Error for {url}: {e}")
            return None, f"Error: {e}"
        finally:
            if client is not self.client:
                await client.aclose()

    def _process_response(
        self, response: httpx.Response
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Process the HTTP response and extract data or error."""
        if response.status_code == 200:
            try:
                return response.json(), None
            except ValueError:
                return None, "Invalid JSON response"
        elif response.status_code == 429:
            return None, "RATE_LIMITED: Rate limit exceeded"
        else:
            return None, f"Error {response.status_code}: {response.text}"
