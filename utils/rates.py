import json
import os
import time
from typing import Any, Dict, Optional, Set, Tuple

from config import CACHE_DURATION, DATA_DIR
from utils.logger import logger
from utils.request_manager import get_request_manager

"""
Cryptocurrency Rates Module
Version: 1.4.0
- Added manual blacklisting mechanism for exchange-ticker pairs
- Added specific blacklist for Monero (XMR) on Binance
- Added tracking for unsupported exchange-ticker pairs
- Implemented caching to avoid retrying failed pairs
- Optimized API requests by skipping known unsupported pairs
- Enhanced caching mechanism for improved performance
- Reduced unnecessary API calls to save resources
"""

# Export variables for external use
__all__ = [
    "get_crypto_price",
    "format_price",
    "format_percent_change",
    "get_cached_price",
    "price_cache",
    "unsupported_pairs",
    "blacklist_pair",
    "unblacklist_pair",
]

# Get the request manager instance
request_manager = get_request_manager()
logger.debug("Using RequestManager for API calls")

# Data directory setup
MARKETS_CACHE_FILE = os.path.join(DATA_DIR, "markets_cache.json")
UNSUPPORTED_PAIRS_FILE = os.path.join(DATA_DIR, "unsupported_pairs.json")

# Cache configuration
price_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # {ticker: (timestamp, data)}

# Unsupported pairs tracking
# Format: {exchange: {ticker1, ticker2, ...}}
unsupported_pairs: Dict[str, Set[str]] = {}


def ensure_data_directory():
    """Create data directory if it doesn't exist."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info(f"Created data directory: {DATA_DIR}")


def get_cached_price(ticker: str) -> Optional[Dict[str, Any]]:
    """Get cached price data if it exists and is not expired."""
    if ticker in price_cache:
        timestamp, data = price_cache[ticker]
        time_diff = time.time() - timestamp
        if time_diff < CACHE_DURATION:
            logger.debug(f"Using cached data for {ticker} (age: {time_diff:.1f}s)")
            return data
        else:
            logger.debug(f"Cached data for {ticker} expired (age: {time_diff:.1f}s)")
    return None


def set_cached_price(ticker: str, data: Dict[str, Any]) -> None:
    """Cache price data with current timestamp."""
    price_cache[ticker] = (time.time(), data)
    logger.debug(f"Cached new data for {ticker}")

    # Save markets cache to file periodically
    # Only save every 10th update to reduce disk I/O
    if len(price_cache) % 10 == 0:
        save_markets_cache()


def load_markets_cache():
    """Load markets cache from file."""
    ensure_data_directory()
    if os.path.exists(MARKETS_CACHE_FILE):
        try:
            with open(MARKETS_CACHE_FILE, "r") as f:
                data = json.load(f)
                # Convert loaded data to proper cache format
                for ticker, ticker_data in data.items():
                    price_cache[ticker] = (
                        ticker_data["timestamp"],
                        ticker_data["data"],
                    )
            logger.debug("Loaded markets cache from file")
        except Exception as e:
            logger.error(f"Error loading markets cache: {e}")
    else:
        logger.info("No markets cache file found")


def save_markets_cache():
    """Save markets cache to file."""
    ensure_data_directory()
    try:
        # Convert cache to serializable format
        serializable_cache = {}
        for ticker, (timestamp, data) in price_cache.items():
            serializable_cache[ticker] = {"timestamp": timestamp, "data": data}

        with open(MARKETS_CACHE_FILE, "w") as f:
            json.dump(serializable_cache, f, indent=2)
        logger.debug(f"Saved markets cache to file ({len(serializable_cache)} entries)")
    except Exception as e:
        logger.error(f"Error saving markets cache: {e}")


def load_unsupported_pairs():
    """Load unsupported pairs from file."""
    ensure_data_directory()
    global unsupported_pairs

    if os.path.exists(UNSUPPORTED_PAIRS_FILE):
        try:
            with open(UNSUPPORTED_PAIRS_FILE, "r") as f:
                data = json.load(f)
                # Convert loaded data to sets for efficient lookups
                unsupported_pairs = {
                    exchange: set(tickers) for exchange, tickers in data.items()
                }
            logger.info(
                f"Loaded unsupported pairs from file: {sum(len(pairs) for pairs in unsupported_pairs.values())} pairs"
            )
        except Exception as e:
            logger.error(f"Error loading unsupported pairs: {e}")
            unsupported_pairs = {}
    else:
        logger.info("No unsupported pairs file found, creating new one")
        unsupported_pairs = {}
        save_unsupported_pairs()


# Initialize manual blacklist entries
def initialize_manual_blacklist():
    """
    Initialize manual blacklist entries for specific exchange-ticker pairs.
    This ensures certain pairs are always marked as unsupported, even if they
    might work technically, for regulatory or other reasons.

    Version: 1.0.0
    - Added initial implementation
    - Blacklisted Monero (XMR) on Binance
    """
    # Cryptocurrencies to blacklist on specific exchanges
    manual_blacklist = {
        "Binance": ["XMR"],  # Monero is blacklisted on Binance
    }

    # Apply the manual blacklist
    for exchange, tickers in manual_blacklist.items():
        for ticker in tickers:
            if not is_pair_unsupported(exchange, ticker):
                mark_pair_as_unsupported(exchange, ticker)
                logger.info(f"Manually blacklisted {ticker} on {exchange}")


# Last save timestamp to avoid excessive disk I/O
_last_unsupported_save = 0


def save_unsupported_pairs():
    """Save unsupported pairs to file, with rate limiting."""
    global _last_unsupported_save

    # Only save if 60 seconds have passed since last save
    current_time = time.time()
    if current_time - _last_unsupported_save < 60:
        logger.debug("Skipping unsupported pairs save (rate limited)")
        return

    ensure_data_directory()
    try:
        # Convert sets to lists for JSON serialization
        serializable_data = {
            exchange: list(tickers) for exchange, tickers in unsupported_pairs.items()
        }

        with open(UNSUPPORTED_PAIRS_FILE, "w") as f:
            json.dump(serializable_data, f, indent=2)

        # Update last save timestamp
        _last_unsupported_save = current_time

        # Count total entries
        total_entries = sum(len(tickers) for tickers in serializable_data.values())
        logger.debug(f"Saved unsupported pairs to file ({total_entries} entries)")
    except Exception as e:
        logger.error(f"Error saving unsupported pairs: {e}")


def is_pair_unsupported(exchange: str, ticker: str) -> bool:
    """Check if a ticker is known to be unsupported by an exchange."""
    return exchange in unsupported_pairs and ticker in unsupported_pairs[exchange]


def mark_pair_as_unsupported(exchange: str, ticker: str, error: str = None):
    """
    Mark a ticker as unsupported by an exchange.

    Args:
        exchange: The exchange name
        ticker: The ticker symbol
        error: Optional error message that caused the marking
    """
    # Skip marking as unsupported if the error is rate-limit related
    if error and ("rate limit" in error.lower() or "429" in error):
        logger.info(
            f"Not marking {ticker} as unsupported on {exchange} due to rate limiting"
        )
        return

    if exchange not in unsupported_pairs:
        unsupported_pairs[exchange] = set()

    if ticker not in unsupported_pairs[exchange]:
        unsupported_pairs[exchange].add(ticker)
        logger.info(f"Marked {ticker} as unsupported on {exchange}")
        # Save periodically, function will rate-limit itself
        save_unsupported_pairs()


def blacklist_pair(exchange: str, ticker: str) -> bool:
    """
    Blacklist a specific ticker from an exchange.
    This is a programmatic way to manually mark pairs as unsupported.

    Args:
        exchange: The exchange name to blacklist from
        ticker: The ticker symbol to blacklist

    Returns:
        bool: True if blacklisted successfully, False if already blacklisted
    """
    ticker = ticker.upper()

    if is_pair_unsupported(exchange, ticker):
        logger.debug(f"{ticker} is already blacklisted on {exchange}")
        return False

    mark_pair_as_unsupported(exchange, ticker)
    logger.info(f"Manually blacklisted {ticker} on {exchange}")
    return True


def unblacklist_pair(exchange: str, ticker: str) -> bool:
    """
    Remove a ticker from the blacklist for an exchange.
    This allows previously blacklisted pairs to be queried again.

    Args:
        exchange: The exchange name
        ticker: The ticker symbol to unblacklist

    Returns:
        bool: True if unblacklisted successfully, False if not blacklisted
    """
    ticker = ticker.upper()

    if not is_pair_unsupported(exchange, ticker):
        logger.debug(f"{ticker} is not blacklisted on {exchange}")
        return False

    if exchange in unsupported_pairs and ticker in unsupported_pairs[exchange]:
        unsupported_pairs[exchange].remove(ticker)
        logger.info(f"Removed {ticker} from blacklist on {exchange}")
        save_unsupported_pairs()
        return True

    return False


# Load cache and unsupported pairs on module import
try:
    load_markets_cache()
    load_unsupported_pairs()
    initialize_manual_blacklist()  # Apply manual blacklist after loading from file
except Exception as e:
    logger.error(f"Failed to load cache data: {e}")


# Function to get price for any ticker from FX Rates API
def get_fxratesapi_price(ticker):
    ticker = ticker.upper()

    # List of supported cryptocurrencies in FX Rates API
    # Based on the sample response
    supported_cryptos = [
        "BTC",
        "ETH",
        "ADA",
        "XRP",
        "BNB",
        "SOL",
        "DOT",
        "LTC",
        "TRX",
        "DAI",
        "OP",
        "ARB",
    ]

    if ticker not in supported_cryptos:
        return None, f"Ticker {ticker} not supported by FX Rates API"

    try:
        # Get rates with USD as base
        response, error = request_manager.get("https://api.fxratesapi.com/latest")

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()

            if data.get("success") and "rates" in data and ticker in data["rates"]:
                # FX Rates API returns inverted rates (USD as base)
                # So we need to calculate 1/rate to get the USD price
                inverted_rate = data["rates"][ticker]
                if inverted_rate > 0:
                    price = 1 / inverted_rate

                    # Unfortunately, the API doesn't provide 24h change data
                    # So we'll set it to None
                    change_24h = None

                    result = {"price": price, "change_24h": change_24h}
                    return result, None
                else:
                    return None, "Invalid rate value (zero or negative)"

            return None, f"Ticker {ticker} not found in response"

        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# CoinGecko API - Free public API
def coingecko_rates():
    try:
        logger.debug("Fetching BTC price from CoinGecko")
        response, error = request_manager.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        )

        if error:
            logger.warning(f"CoinGecko API error: {error}")
            return {}

        if response and response.status_code == 200:
            data = response.json()
            # Format as rates with BTC as the key for consistency
            rates = {"BTC": data["bitcoin"]["usd"]}
            logger.debug(f"CoinGecko BTC: {rates['BTC']}")
            return rates
        else:
            status_code = response.status_code if response else "N/A"
            logger.warning(f"CoinGecko API error: {status_code}")
            return {}
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return {}


# CryptoCompare API - Free public API
def cryptocompare_rates():
    try:
        logger.debug("Fetching BTC price from CryptoCompare")
        response, error = request_manager.get(
            "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD"
        )

        if error:
            logger.warning(f"CryptoCompare API error: {error}")
            return {}

        if response and response.status_code == 200:
            data = response.json()
            # Format as rates with BTC as the key for consistency
            rates = {"BTC": data["USD"]}  # Direct price, not inverted
            logger.debug(f"CryptoCompare BTC: {rates['BTC']}")
            return rates
        else:
            status_code = response.status_code if response else "N/A"
            logger.warning(f"CryptoCompare API error: {status_code}")
            return {}
    except Exception as e:
        logger.error(f"CryptoCompare error: {e}")
        return {}


# Function to get price for any ticker from CoinGecko
def get_coingecko_price(ticker):
    # Map of common ticker symbols to CoinGecko IDs
    ticker_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "TON": "the-open-network",
        "DOGE": "dogecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOT": "polkadot",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "LTC": "litecoin",
        "VET": "vechain",
        "TRX": "tron",
        "XMR": "monero",
        "BNB": "binancecoin",
        "NOT": "not-financial-advice",  # New token
        "MAJOR": "major-protocol",  # New token
    }

    ticker = ticker.upper()

    # Get coin ID for CoinGecko API
    coin_id = ticker_map.get(ticker)
    if not coin_id:
        return None, f"Ticker {ticker} not mapped for CoinGecko"

    try:
        # Updated to include 24h change data
        response, error = request_manager.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        )

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()
            if coin_id in data and "usd" in data[coin_id]:
                price = data[coin_id]["usd"]
                # Get 24h change if available
                change_24h = data[coin_id].get("usd_24h_change", None)
                result = {"price": price, "change_24h": change_24h}
                return result, None
            return None, "Coin data not found in response"
        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from CryptoCompare
def get_cryptocompare_price(ticker):
    ticker = ticker.upper()

    try:
        # Updated to include 24h change
        response, error = request_manager.get(
            f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={ticker}&tsyms=USD"
        )

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()
            if "RAW" in data and ticker in data["RAW"] and "USD" in data["RAW"][ticker]:
                raw_data = data["RAW"][ticker]["USD"]
                price = raw_data["PRICE"]
                # Get 24h change percentage
                change_24h = raw_data.get("CHANGEPCT24HOUR", None)
                result = {"price": price, "change_24h": change_24h}
                return result, None
            elif "Message" in data:
                return None, data["Message"]
            return None, "Price not found in response"
        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Binance
def get_binance_price(ticker):
    ticker = ticker.upper()

    # Check if this ticker is already known to be unsupported by Binance
    if is_pair_unsupported("Binance", ticker):
        logger.debug(f"Skipping {ticker} on Binance (known unsupported pair)")
        return None, f"Ticker {ticker} is known to be unsupported by Binance"

    # Try different market pairs
    pairs = [f"{ticker}USDT", f"{ticker}BUSD", f"{ticker}USD", f"{ticker}USDC"]

    try:
        logger.debug(f"Fetching {ticker} price from Binance...")

        # Collect error messages
        final_error = None

        # Try each pair format
        for pair in pairs:
            logger.debug(f"Trying Binance pair: {pair}")

            # Get 24hr ticker price change statistics
            response, error = request_manager.get(
                f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
            )

            if error:
                logger.debug(f"Binance API error for {pair}: {error}")
                final_error = error  # Store the last error
                continue

            if response and response.status_code == 200:
                data = response.json()

                # Check if we got a valid response
                if "lastPrice" in data and "priceChangePercent" in data:
                    price = float(data["lastPrice"])
                    # Parse change percentage
                    change_24h = (
                        float(data["priceChangePercent"])
                        if data["priceChangePercent"]
                        else None
                    )
                    result = {"price": price, "change_24h": change_24h}
                    logger.debug(
                        f"Successfully fetched {ticker} price from Binance: {price}"
                    )
                    return result, None

            # If we got a non-200 response or missing data, try next format
            else:
                status = response.status_code if response else "N/A"
                logger.debug(f"Binance API returned {status} for {pair}")
                if response and response.status_code == 429:
                    final_error = "Rate limited"

        # If we've tried all formats and none worked
        logger.warning(f"Could not find valid Binance pair for {ticker}")

        # Mark this ticker as unsupported by Binance, passing the error message
        mark_pair_as_unsupported("Binance", ticker, final_error)
        return None, f"No valid pair found for {ticker} on Binance"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Exception fetching {ticker} from Binance: {error_msg}")
        return None, f"Exception: {error_msg}"


# Function to get price for any ticker from Gate•io
def get_gateio_price(ticker):
    ticker = ticker.upper()

    try:
        # Get ticker info
        response, error = request_manager.get(
            f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={ticker}_USDT"
        )

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                ticker_data = data[0]
                price = float(ticker_data["last"])
                # Calculate 24h change
                change_24h = None
                if "high_24h" in ticker_data and "low_24h" in ticker_data:
                    open_24h = float(ticker_data.get("open_24h", 0))
                    if open_24h > 0:
                        change_24h = ((price - open_24h) / open_24h) * 100

                result = {"price": price, "change_24h": change_24h}
                return result, None
            return None, "No data found in response"
        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Kraken
def get_kraken_price(ticker):
    ticker = ticker.upper()

    # Check if this ticker is already known to be unsupported by Kraken
    if is_pair_unsupported("Kraken", ticker):
        logger.debug(f"Skipping {ticker} on Kraken (known unsupported pair)")
        return None, f"Ticker {ticker} is known to be unsupported by Kraken"

    # Mapping for special Kraken asset pairs
    kraken_special_map = {
        "BTC": "XBT",  # Kraken uses XBT for Bitcoin
        "ETH": "ETH",
        "XRP": "XRP",
        "SOL": "SOL",
        "TON": "TON",
        "DOGE": "DOGE",
        "ADA": "ADA",
        "DOT": "DOT",
        "AVAX": "AVAX",
        "LINK": "LINK",
        "XMR": "XMR",
        "BNB": "BNB",
        "LTC": "LTC",
        "VET": "VET",
        "TRX": "TRX",
        "NOT": "NOT",
        "MAJOR": "MAJOR",
    }

    # Find the Kraken asset code
    asset_code = kraken_special_map.get(ticker, ticker)

    try:
        logger.debug(
            f"Fetching {ticker} price from Kraken using asset code {asset_code}"
        )

        # Collect error messages
        final_error = None

        # Build an array of possible pair formats to try
        pair_formats = [
            f"{asset_code}/USD",  # Modern format (BNB/USD)
            f"{asset_code}USD",  # Standard format (XMRUSD)
            f"{asset_code}USDT",  # USDT pair (XMRUSDT)
            f"X{asset_code}ZUSD",  # With prefixes (XXMRZUSD)
            f"{asset_code}ZUSD",  # Z prefix for USD (XMRZUSD)
            f"X{asset_code}USD",  # X prefix for crypto (XXMRUSD)
        ]

        # Special case for BTC
        if ticker == "BTC":
            pair_formats = ["XXBTZUSD", "XBTUSD", "XBTZUSD", "XBT/USD"] + pair_formats

        # Try each pair format
        for pair_format in pair_formats:
            logger.debug(f"Trying Kraken pair format: {pair_format}")
            response, error = request_manager.get(
                f"https://api.kraken.com/0/public/Ticker?pair={pair_format}"
            )

            if error:
                logger.debug(f"Kraken API error for {pair_format}: {error}")
                final_error = error  # Store the last error
                continue

            if response and response.status_code == 200:
                data = response.json()

                # Check for errors
                if "error" in data and data["error"] and len(data["error"]) > 0:
                    error_msg = data["error"][0]
                    if "Unknown asset pair" in error_msg:
                        logger.debug(
                            f"Kraken pair format {pair_format} not found, trying next"
                        )
                    continue

                # Find the correct key in the result
                if "result" in data and data["result"]:
                    # The API returns the data with the pair name as the key
                    # Find the first key that is not "error" or "result"
                    for key in data["result"]:
                        # Get the current price (last trade closed price)
                        if "c" in data["result"][key]:
                            # First value in the array is the price
                            price = float(data["result"][key]["c"][0])

                            # Try to get 24hr change
                            change_24h = None
                            if "p" in data["result"][key]:
                                # Percentage change calculation
                                # 'p' is price data with [0] being today
                                change_24h = float(data["result"][key]["p"][1])

                            result = {"price": price, "change_24h": change_24h}
                            logger.debug(
                                f"Successfully fetched {ticker} price from Kraken: {price}"
                            )
                            return result, None

            # Check for rate limiting
            if response and response.status_code == 429:
                final_error = "Rate limited"

        # If no matching pair was found after trying all formats
        logger.warning(f"No valid Kraken pair found for {ticker}")

        # Mark this ticker as unsupported by Kraken, passing the error message
        mark_pair_as_unsupported("Kraken", ticker, final_error)
        return None, f"No valid pair found for {ticker} on Kraken"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Exception in Kraken API for {ticker}: {error_msg}")
        return None, f"Exception: {error_msg}"


# Function to get price for any ticker from Huobi
def get_huobi_price(ticker):
    ticker = ticker.lower()

    try:
        # Get market details
        detail_response, detail_error = request_manager.get(
            f"https://api.huobi.pro/market/detail/merged?symbol={ticker}usdt"
        )

        if detail_error:
            return None, f"API error (detail): {detail_error}"

        # Also get market tickers for 24h change
        tickers_response, tickers_error = request_manager.get(
            "https://api.huobi.pro/market/tickers"
        )

        if tickers_error:
            return None, f"API error (tickers): {tickers_error}"

        # Get more detailed 24h stats
        detail_req_response, detail_req_error = request_manager.get(
            f"https://api.huobi.pro/market/detail?symbol={ticker}usdt"
        )

        if (
            detail_response
            and detail_response.status_code == 200
            and tickers_response
            and tickers_response.status_code == 200
        ):
            data = detail_response.json()
            tickers_data = tickers_response.json()

            # Check if we have detail data available
            detail_data = None
            if detail_req_response and detail_req_response.status_code == 200:
                detail_data = detail_req_response.json()
                logger.debug(f"Huobi detail data for {ticker}: {detail_data}")

            if "status" in data and data["status"] == "ok" and "tick" in data:
                price = float(data["tick"]["close"])

                # Find ticker in all tickers to get 24h change
                change_24h = None

                # Try to calculate from detail endpoint first (more accurate)
                if (
                    detail_data
                    and "status" in detail_data
                    and detail_data["status"] == "ok"
                    and "tick" in detail_data
                ):
                    detail_tick = detail_data["tick"]
                    if "open" in detail_tick and detail_tick["open"] > 0:
                        # Use open and close from the detailed 24h data
                        open_price = float(detail_tick["open"])
                        change_24h = ((price - open_price) / open_price) * 100
                        logger.debug(
                            f"Huobi 24h change calculated from detail endpoint: {change_24h}%"
                        )

                # Fallback to tickers endpoint
                if change_24h is None and "data" in tickers_data:
                    for item in tickers_data["data"]:
                        if item.get("symbol") == f"{ticker}usdt":
                            # Calculate percent change using close and open price
                            if (
                                "open" in item
                                and item["open"] > 0
                                and "close" in item
                                and item["close"] > 0
                            ):
                                open_price = float(item["open"])
                                close_price = float(item["close"])
                                change_24h = (
                                    (close_price - open_price) / open_price
                                ) * 100
                                logger.debug(
                                    f"Huobi 24h change calculated from tickers endpoint: {change_24h}%"
                                )
                            break

                # If we calculated a change but it seems off, try the data from the merged endpoint
                if (change_24h is None or abs(change_24h) < 0.5) and "tick" in data:
                    tick_data = data["tick"]
                    if "open" in tick_data and tick_data["open"] > 0:
                        open_price = float(tick_data["open"])
                        change_24h = ((price - open_price) / open_price) * 100
                        logger.debug(
                            f"Huobi 24h change calculated from merged endpoint: {change_24h}%"
                        )

                result = {"price": price, "change_24h": change_24h}
                return result, None
            elif "err-msg" in data:
                return None, data["err-msg"]
            return None, "Price not found in response"
        status_codes = f"{detail_response.status_code if detail_response else 'N/A'}/{tickers_response.status_code if tickers_response else 'N/A'}"
        return None, f"Error {status_codes}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Format price with commas for thousands and 2 decimal places
def format_price(price):
    if price is None:
        return "N/A"
    if price >= 1:
        return f"${price:,.3f}"
    elif price >= 0.10:
        return f"${price:,.4f}"
    elif price >= 0.01:
        return f"${price:,.5f}"
    else:
        return f"${price:,.6f}"


# Format percentage change with color indicators and proper decimal places
def format_percent_change(change):
    if change is None:
        return "N/A"

    # Format with 2 decimal places
    formatted = f"{change:.2f}%"

    # Add + sign for positive changes
    if change > 0:
        return f"+{formatted}"
    return formatted


# Function to get price for any ticker from OKX
def get_okx_price(ticker):
    ticker = ticker.upper()

    try:
        # Get ticker info for spot market
        response, error = request_manager.get(
            f"https://www.okx.com/api/v5/market/ticker?instId={ticker}-USDT"
        )

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()
            if data.get("code") == "0" and "data" in data and len(data["data"]) > 0:
                ticker_data = data["data"][0]

                # Get current price
                price = float(ticker_data.get("last", 0))

                # Calculate 24h change from open/close
                change_24h = None
                open_24h = float(ticker_data.get("open24h", 0))
                if open_24h > 0 and price > 0:
                    change_24h = ((price - open_24h) / open_24h) * 100

                result = {"price": price, "change_24h": change_24h}
                return result, None

            # Handle error message in response
            if "msg" in data and data["msg"]:
                return None, f"OKX API error: {data['msg']}"

            return None, "No data found in response"

        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from KuCoin
def get_kucoin_price(ticker):
    ticker = ticker.upper()

    try:
        # Get current ticker price
        price_response, price_error = request_manager.get(
            f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={ticker}-USDT"
        )

        if price_error:
            return None, f"API error (price): {price_error}"

        # Get 24h stats
        stats_response, stats_error = request_manager.get(
            f"https://api.kucoin.com/api/v1/market/stats?symbol={ticker}-USDT"
        )

        if stats_error:
            return None, f"API error (stats): {stats_error}"

        if (
            price_response
            and price_response.status_code == 200
            and stats_response
            and stats_response.status_code == 200
        ):
            price_data = price_response.json()
            stats_data = stats_response.json()

            if price_data.get("code") == "200000" and "data" in price_data:
                price_info = price_data["data"]
                price = float(price_info.get("price", 0))

                # Get 24h change from stats
                change_24h = None
                if stats_data.get("code") == "200000" and "data" in stats_data:
                    stats_info = stats_data["data"]
                    open_price = float(stats_info.get("openPrice", 0))
                    if open_price > 0 and price > 0:
                        change_24h = ((price - open_price) / open_price) * 100

                result = {"price": price, "change_24h": change_24h}
                return result, None

            # Handle error message in response
            for data in [price_data, stats_data]:
                if "msg" in data and data["msg"]:
                    return None, f"KuCoin API error: {data['msg']}"

            return None, "No price data found in response"

        status_codes = f"{price_response.status_code if price_response else 'N/A'}/{stats_response.status_code if stats_response else 'N/A'}"
        return None, f"Error {status_codes}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Bybit
def get_bybit_price(ticker):
    ticker = ticker.upper()

    try:
        # Get ticker info
        response, error = request_manager.get(
            f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={ticker}USDT"
        )

        if error:
            return None, f"API error: {error}"

        if response and response.status_code == 200:
            data = response.json()

            if (
                data.get("retCode") == 0
                and "result" in data
                and "list" in data["result"]
            ):
                ticker_list = data["result"]["list"]

                if ticker_list and len(ticker_list) > 0:
                    ticker_data = ticker_list[0]
                    price = float(ticker_data.get("lastPrice", 0))

                    # Calculate 24h change
                    change_24h = None
                    if (
                        "prevPrice24h" in ticker_data
                        and float(ticker_data["prevPrice24h"]) > 0
                    ):
                        prev_price = float(ticker_data["prevPrice24h"])
                        change_24h = ((price - prev_price) / prev_price) * 100

                    result = {"price": price, "change_24h": change_24h}
                    return result, None

            # Handle error message
            if "retMsg" in data and data["retMsg"] != "OK":
                return None, f"Bybit API error: {data['retMsg']}"

            return None, "No ticker data found in response"

        return (
            None,
            f"Error {response.status_code if response else 'N/A'}: {response.text if response else 'No response'}",
        )
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function that fetches a ticker price from all APIs
def get_crypto_price(ticker):
    """Get cryptocurrency price data with caching and optimized API usage."""
    # Check if we have cached data first
    cached_data = get_cached_price(ticker)
    if cached_data:
        logger.info(f"Using cached data for {ticker}")
        return cached_data

    logger.info(f"Fetching {ticker} prices from external sources...")

    # Store prices for calculating average
    prices = []
    change_24h_values = []
    active_sources = 0
    skipped_sources = 0
    source_data = {}

    # CoinGecko
    if not is_pair_unsupported("CoinGecko", ticker):
        result, error = get_coingecko_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["CoinGecko"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"CoinGecko: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"CoinGecko does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("CoinGecko", ticker, error)
    else:
        logger.debug(f"Skipping CoinGecko for {ticker} (known unsupported)")
        skipped_sources += 1

    # Gate•io
    if not is_pair_unsupported("Gate•io", ticker):
        result, error = get_gateio_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["Gate•io"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"Gate•io: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"Gate•io does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("Gate•io", ticker, error)
    else:
        logger.debug(f"Skipping Gate•io for {ticker} (known unsupported)")
        skipped_sources += 1

    # CryptoCompare
    if not is_pair_unsupported("CryptoCompare", ticker):
        result, error = get_cryptocompare_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["CryptoCompare"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"CryptoCompare: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"CryptoCompare does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("CryptoCompare", ticker, error)
    else:
        logger.debug(f"Skipping CryptoCompare for {ticker} (known unsupported)")
        skipped_sources += 1

    # Binance
    if not is_pair_unsupported("Binance", ticker):
        result, error = get_binance_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["Binance"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"Binance: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"Binance does not have ticker {ticker} - {error}")
            # Note: Binance function now marks pairs as unsupported itself
    else:
        logger.debug(f"Skipping Binance for {ticker} (known unsupported)")
        skipped_sources += 1

    # Kraken
    if not is_pair_unsupported("Kraken", ticker):
        result, error = get_kraken_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["Kraken"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"Kraken: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"Kraken does not have ticker {ticker} - {error}")
            # Note: Kraken function now marks pairs as unsupported itself
    else:
        logger.debug(f"Skipping Kraken for {ticker} (known unsupported)")
        skipped_sources += 1

    # Huobi
    if not is_pair_unsupported("Huobi", ticker):
        result, error = get_huobi_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["Huobi"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"Huobi: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"Huobi does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("Huobi", ticker, error)
    else:
        logger.debug(f"Skipping Huobi for {ticker} (known unsupported)")
        skipped_sources += 1

    # OKX (new)
    if not is_pair_unsupported("OKX", ticker):
        result, error = get_okx_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["OKX"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"OKX: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"OKX does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("OKX", ticker, error)
    else:
        logger.debug(f"Skipping OKX for {ticker} (known unsupported)")
        skipped_sources += 1

    # KuCoin (new)
    if not is_pair_unsupported("KuCoin", ticker):
        result, error = get_kucoin_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["KuCoin"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"KuCoin: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"KuCoin does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("KuCoin", ticker, error)
    else:
        logger.debug(f"Skipping KuCoin for {ticker} (known unsupported)")
        skipped_sources += 1

    # Bybit (new)
    if not is_pair_unsupported("Bybit", ticker):
        result, error = get_bybit_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["Bybit"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"Bybit: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"Bybit does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("Bybit", ticker, error)
    else:
        logger.debug(f"Skipping Bybit for {ticker} (known unsupported)")
        skipped_sources += 1

    # FX Rates (new) - forex and some crypto rates
    if not is_pair_unsupported("FX Rates", ticker):
        result, error = get_fxratesapi_price(ticker)
        if result is not None:
            prices.append(result["price"])
            if result["change_24h"] is not None:
                change_24h_values.append(result["change_24h"])
            active_sources += 1
            source_data["FX Rates"] = {
                "price": result["price"],
                "change_24h": result["change_24h"],
            }
            logger.debug(
                f"FX Rates: {format_price(result['price'])} ({format_percent_change(result['change_24h'])})"
            )
        else:
            logger.warning(f"FX Rates does not have ticker {ticker} - {error}")
            # Pass the error to mark_pair_as_unsupported
            mark_pair_as_unsupported("FX Rates", ticker, error)
    else:
        logger.debug(f"Skipping FX Rates for {ticker} (known unsupported)")
        skipped_sources += 1

    # Calculate and return average price and average 24h change
    result = {
        "ticker": ticker,
        "sources": source_data,
        "active_sources": active_sources,
        "skipped_sources": skipped_sources,
        "timestamp": time.time(),  # Add timestamp for reference
    }

    if active_sources > 0:
        average_price = sum(prices) / active_sources
        result["average_price"] = average_price

        # Calculate average 24h change if available
        if change_24h_values:
            average_change_24h = sum(change_24h_values) / len(change_24h_values)
            result["average_change_24h"] = average_change_24h
            logger.info(
                f"{ticker}: {format_price(average_price)} ({format_percent_change(average_change_24h)}) from {active_sources} sources"
            )
        else:
            result["average_change_24h"] = None
            logger.info(
                f"{ticker}: {format_price(average_price)} (no change data) from {active_sources} sources"
            )
    else:
        result["average_price"] = None
        result["average_change_24h"] = None
        logger.warning(f"Unable to fetch {ticker} price from any source")

    # Cache the result
    set_cached_price(ticker, result)

    return result
