import sys
import json

import httpx
from loguru import logger

# Configure Loguru with colors
logger.remove()  # Remove default handler
logger.configure(
    handlers=[
        {
            "sink": sys.stderr,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            "colorize": True,
        }
    ]
)

# Load configuration
with open("config.json", "r") as config_file:
    config = json.load(config_file)
    logger.debug(f"Loaded rates configuration: {config}")

# Initialize HTTP client
sess = httpx.Client(timeout=config.get("timeout", 10))
logger.debug(
    f"Initialized HTTP client with timeout of {config.get('timeout', 10)} seconds"
)


# CoinGecko API - Free public API
def coingecko_rates():
    try:
        logger.debug("Fetching BTC price from CoinGecko")
        req = sess.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        )

        if req.status_code == 200:
            data = req.json()
            # Format as rates with BTC as the key for consistency
            rates = {"BTC": data["bitcoin"]["usd"]}
            logger.debug(f"CoinGecko BTC: {rates['BTC']}")
            return rates
        else:
            logger.warning(f"CoinGecko API error: {req.status_code}")
            return {}
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return {}


# CryptoCompare API - Free public API
def cryptocompare_rates():
    try:
        logger.debug("Fetching BTC price from CryptoCompare")
        req = sess.get(
            "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD"
        )

        if req.status_code == 200:
            data = req.json()
            # Format as rates with BTC as the key for consistency
            rates = {"BTC": data["USD"]}  # Direct price, not inverted
            logger.debug(f"CryptoCompare BTC: {rates['BTC']}")
            return rates
        else:
            logger.warning(f"CryptoCompare API error: {req.status_code}")
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
    }

    ticker = ticker.upper()

    # Get coin ID for CoinGecko API
    coin_id = ticker_map.get(ticker)
    if not coin_id:
        return None, f"Ticker {ticker} not mapped for CoinGecko"

    try:
        # Updated to include 24h change data
        req = sess.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        )

        if req.status_code == 200:
            data = req.json()
            if coin_id in data and "usd" in data[coin_id]:
                price = data[coin_id]["usd"]
                # Get 24h change if available
                change_24h = data[coin_id].get("usd_24h_change", None)
                result = {"price": price, "change_24h": change_24h}
                return result, None
            return None, "Coin data not found in response"
        return None, f"Error {req.status_code}: {req.text}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from CryptoCompare
def get_cryptocompare_price(ticker):
    ticker = ticker.upper()

    try:
        # Updated to include 24h change
        req = sess.get(
            f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={ticker}&tsyms=USD"
        )

        if req.status_code == 200:
            data = req.json()
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
        return None, f"Error {req.status_code}: {req.text}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Binance
def get_binance_price(ticker):
    ticker = ticker.upper()

    # Blacklist for tokens delisted from Binance
    binance_blacklist = ["XMR"]

    # Check if ticker is blacklisted for Binance
    if ticker in binance_blacklist:
        return None, f"Token {ticker} is delisted or not available on Binance"

    try:
        # First get the current price
        price_req = sess.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={ticker}USDT"
        )

        # Then get 24h statistics
        ticker_req = sess.get(
            f"https://api.binance.com/api/v3/ticker/24hr?symbol={ticker}USDT"
        )

        if price_req.status_code == 200 and ticker_req.status_code == 200:
            price_data = price_req.json()
            ticker_data = ticker_req.json()

            if "price" in price_data:
                price = float(price_data["price"])
                # Calculate percent change using price change and price
                change_24h = None
                if "priceChangePercent" in ticker_data:
                    change_24h = float(ticker_data["priceChangePercent"])

                result = {"price": price, "change_24h": change_24h}
                return result, None
            return None, "Price not found in response"
        elif price_req.status_code == 400 or ticker_req.status_code == 400:
            return None, f"Invalid symbol {ticker}USDT"
        return None, f"Error {price_req.status_code}/{ticker_req.status_code}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Kraken
def get_kraken_price(ticker):
    ticker = ticker.upper()

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
        "XMR": "XMR",  # Fixed, Kraken uses XMR not XXMR
        "BNB": "BNB",
    }

    # Find the Kraken asset code
    asset_code = kraken_special_map.get(ticker, ticker)

    try:
        logger.debug(
            f"Fetching {ticker} price from Kraken using asset code {asset_code}"
        )

        # Build an array of possible pair formats to try
        pair_formats = [
            f"{asset_code}USD",  # Standard format (XMRUSD)
            f"{asset_code}USDT",  # USDT pair (XMRUSDT)
            f"X{asset_code}ZUSD",  # With prefixes (XXMRZUSD)
            f"{asset_code}ZUSD",  # Z prefix for USD (XMRZUSD)
            f"X{asset_code}USD",  # X prefix for crypto (XXMRUSD)
        ]

        # Special case for BTC
        if ticker == "BTC":
            pair_formats = ["XXBTZUSD", "XBTUSD", "XBTZUSD"] + pair_formats

        # Try each pair format
        for pair_format in pair_formats:
            logger.debug(f"Trying Kraken pair format: {pair_format}")
            req = sess.get(f"https://api.kraken.com/0/public/Ticker?pair={pair_format}")

            if req.status_code == 200:
                data = req.json()

                # Check for errors
                if "error" in data and data["error"] and len(data["error"]) > 0:
                    error_msg = data["error"][0]
                    if "Unknown asset pair" in error_msg:
                        logger.debug(
                            f"Kraken pair format {pair_format} not found, trying next"
                        )
                        continue
                    else:
                        logger.warning(f"Kraken API error for {ticker}: {error_msg}")
                        return None, error_msg

                # If no errors, check results
                if "result" in data and data["result"]:
                    # Check if this specific pair format exists in results
                    if pair_format in data["result"]:
                        price = float(data["result"][pair_format]["c"][0])
                        change_24h = None  # Kraken doesn't provide 24h change directly
                        result = {"price": price, "change_24h": change_24h}
                        logger.info(
                            f"Successfully fetched {ticker} price from Kraken: {price}"
                        )
                        return result, None

                    # If the pair doesn't match exactly, but we have results, use the first one
                    if data["result"] and len(data["result"]) > 0:
                        first_pair = list(data["result"].keys())[0]
                        price = float(data["result"][first_pair]["c"][0])
                        change_24h = None
                        result = {"price": price, "change_24h": change_24h}
                        logger.info(
                            f"Successfully fetched {ticker} price from Kraken using first pair ({first_pair}): {price}"
                        )
                        return result, None

            # If we got a non-200 response, try the next format
            else:
                logger.debug(f"Kraken API returned {req.status_code} for {pair_format}")

        # If we've tried all formats and none worked
        logger.warning(f"Could not find valid Kraken pair format for {ticker}")
        return None, f"No valid pair format found for {ticker} on Kraken"

    except Exception as e:
        logger.error(f"Exception fetching {ticker} from Kraken: {e}")
        return None, f"Exception: {str(e)}"


# Function to get price for any ticker from Huobi
def get_huobi_price(ticker):
    ticker = ticker.lower()

    try:
        # Get market details
        req = sess.get(
            f"https://api.huobi.pro/market/detail/merged?symbol={ticker}usdt"
        )

        # Also get market tickers for 24h change
        tickers_req = sess.get("https://api.huobi.pro/market/tickers")

        # Get more detailed 24h stats
        detail_req = sess.get(
            f"https://api.huobi.pro/market/detail?symbol={ticker}usdt"
        )

        if req.status_code == 200 and tickers_req.status_code == 200:
            data = req.json()
            tickers_data = tickers_req.json()

            # Check if we have detail data available
            detail_data = None
            if detail_req.status_code == 200:
                detail_data = detail_req.json()
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
        return None, f"Error {req.status_code}/{tickers_req.status_code}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


# Format price with commas for thousands and 2 decimal places
def format_price(price):
    if price is None:
        return "N/A"
    return f"${price:,.2f}" if price >= 0.01 else f"${price:.8f}"


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


# Function that fetches a ticker price from all APIs
def get_crypto_price(ticker):
    logger.info(f"Fetching {ticker} prices...")

    # Store prices for calculating average
    prices = []
    change_24h_values = []
    active_sources = 0
    source_data = {}

    # CoinGecko
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

    # CryptoCompare
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

    # Binance
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

    # Kraken
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

    # Huobi
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

    # Calculate and return average price and average 24h change
    result = {
        "ticker": ticker,
        "sources": source_data,
        "active_sources": active_sources,
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

    return result
