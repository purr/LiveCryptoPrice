"""
Request Manager for LiveCryptoPrice bot.
Handles API requests with proper error handling and rate limiting support.
"""

import time
from typing import Dict, Tuple, TypeVar, Optional

import httpx
from httpx import Response

from config import TIMEOUT
from utils.logger import logger

# Type variable for generic functions
T = TypeVar("T")


class RequestManager:
    """
    Handles API requests with proper error handling, retry logic, and rate limit support.
    Uses httpx client for HTTP requests with configured timeout.
    """

    def __init__(self):
        """Initialize the RequestManager with an httpx client."""
        self.client = httpx.Client(timeout=TIMEOUT)
        self.async_client = None  # Lazy-initialized
        self.rate_limited_until: Dict[str, float] = {}  # domain -> timestamp
        logger.debug(f"Initialized RequestManager with timeout of {TIMEOUT} seconds")

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for rate limit tracking."""
        try:
            if "://" in url:
                domain = url.split("://")[1].split("/")[0]
            else:
                domain = url.split("/")[0]
            return domain
        except Exception:
            # If we can't extract domain, use the full URL
            return url

    def _is_rate_limited(self, url: str) -> bool:
        """Check if a domain is currently rate limited."""
        domain = self._get_domain(url)
        if domain in self.rate_limited_until:
            if time.time() < self.rate_limited_until[domain]:
                logger.warning(f"Domain {domain} is rate limited, skipping request")
                return True
            else:
                # Rate limit has expired
                del self.rate_limited_until[domain]
        return False

    def _handle_rate_limit(self, url: str, retry_after: Optional[int] = None) -> None:
        """
        Mark a domain as rate limited for a specified duration.

        Args:
            url: The URL that received a rate limit response
            retry_after: Seconds to wait before trying again (default 60)
        """
        domain = self._get_domain(url)

        # If Retry-After header wasn't provided, use default value
        if retry_after is None or retry_after <= 0:
            retry_after = 60

        # Set rate limit expiry time
        self.rate_limited_until[domain] = time.time() + retry_after
        logger.warning(f"Rate limited on {domain} for {retry_after} seconds")

    def get(self, url: str) -> Tuple[Optional[Response], Optional[str]]:
        """
        Make a GET request, handling rate limits.

        Returns:
            Tuple of (response, error_message)
            If rate limited or error, response will be None
        """
        logger.debug(f"Making GET request to {url}")
        if self._is_rate_limited(url):
            return None, "Rate limited"

        try:
            response = self.client.get(url)

            # Handle rate limiting
            if response.status_code == 429:
                # Try to get retry-after header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        retry_after = int(retry_after)
                    except ValueError:
                        # If it's a date, just use default
                        retry_after = 60
                else:
                    retry_after = 60

                self._handle_rate_limit(url, retry_after)
                return None, f"Rate limited for {retry_after} seconds"

            return response, None

        except httpx.TimeoutException:
            return None, "Request timed out"
        except httpx.RequestError as e:
            return None, f"Request error: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error: {str(e)}"

    async def _ensure_async_client(self):
        """Ensure async client is initialized."""
        if self.async_client is None:
            self.async_client = httpx.AsyncClient(timeout=TIMEOUT)

    async def get_async(self, url: str) -> Tuple[Optional[Response], Optional[str]]:
        """
        Make an asynchronous GET request, handling rate limits.

        Returns:
            Tuple of (response, error_message)
            If rate limited or error, response will be None
        """
        if self._is_rate_limited(url):
            return None, "Rate limited"

        try:
            await self._ensure_async_client()
            response = await self.async_client.get(url)

            # Handle rate limiting
            if response.status_code == 429:
                # Try to get retry-after header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        retry_after = int(retry_after)
                    except ValueError:
                        # If it's a date, just use default
                        retry_after = 60
                else:
                    retry_after = 60

                self._handle_rate_limit(url, retry_after)
                return None, f"Rate limited for {retry_after} seconds"

            return response, None

        except httpx.TimeoutException:
            return None, "Request timed out"
        except httpx.RequestError as e:
            return None, f"Request error: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error: {str(e)}"

    def close(self):
        """Close the HTTP client connections."""
        self.client.close()

    async def close_async(self):
        """Close the async HTTP client if it was initialized."""
        if self.async_client is not None:
            await self.async_client.aclose()


# Global request manager instance
request_manager = RequestManager()


def get_request_manager() -> RequestManager:
    """Get the global request manager instance."""
    return request_manager
