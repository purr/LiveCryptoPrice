from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from blacklist import BlacklistManager
from main import CryptoPrice


class ApiError(Exception):
    """Base class for API errors"""

    pass


class RateLimitError(ApiError):
    """Raised when rate limit is exceeded"""

    pass


class UnknownAssetError(ApiError):
    """Raised when asset is not found or not supported"""

    pass


class ExchangeConnector(ABC):
    """Base class for all exchange connectors"""

    name: str
    base_url: str

    def __init__(self, blacklist_manager: Optional[BlacklistManager] = None):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.blacklist_manager = blacklist_manager

    async def close(self):
        await self.client.aclose()

    @abstractmethod
    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        """Get price data for a specific ticker"""
        pass

    async def handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response and check for errors

        Args:
            response: The API response

        Returns:
            Response data

        Raises:
            RateLimitError: If rate limit is exceeded
            UnknownAssetError: If asset is not found
            ApiError: For other API errors
        """
        # Check for rate limit first (HTTP 429)
        if response.status_code == 429:
            raise RateLimitError(f"Rate limit exceeded for {self.name}")

        # Other errors
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            # Try to determine if this is an unknown asset error
            if response.status_code == 400 or response.status_code == 404:
                error_text = response.text.lower()
                if any(
                    term in error_text
                    for term in ["unknown", "not found", "invalid", "pair", "symbol"]
                ):
                    raise UnknownAssetError(
                        f"Unknown asset or trading pair on {self.name}: {response.text}"
                    )
            raise ApiError(f"API error: {e}")

    def check_blacklist(self, symbol: str) -> bool:
        """
        Check if a symbol is blacklisted for this exchange

        Args:
            symbol: The cryptocurrency symbol

        Returns:
            True if blacklisted, False if not
        """
        if self.blacklist_manager is None:
            return False

        return self.blacklist_manager.is_ticker_blacklisted(symbol, self.name)

    def add_to_blacklist(self, symbol: str):
        """
        Add a symbol to the blacklist for this exchange

        Args:
            symbol: The cryptocurrency symbol
        """
        if self.blacklist_manager is not None:
            self.blacklist_manager.add_to_blacklist(symbol, self.name)
            logger.info(f"Added {symbol} to blacklist for exchange {self.name}")


class BinanceConnector(ExchangeConnector):
    name = "binance"
    base_url = "https://api.binance.com/api/v3"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to Binance format (append USDT)
            binance_symbol = f"{symbol}USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/ticker/24hr", params={"symbol": binance_symbol}
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            return CryptoPrice(
                price=Decimal(data["lastPrice"]),
                volume_24h=Decimal(data["quoteVolume"]),
                change_24h=Decimal(data["priceChangePercent"]),
                exchange=self.name,
            )
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class KrakenConnector(ExchangeConnector):
    name = "kraken"
    base_url = "https://api.kraken.com/0/public"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to Kraken format
            if symbol == "BTC":
                kraken_symbol = "XBTUSDT"
            else:
                kraken_symbol = f"{symbol}USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/Ticker", params={"pair": kraken_symbol}
            )
            data = response.json()

            # Check for Kraken specific errors
            if data["error"]:
                error_message = str(data["error"]).lower()
                if "unknown asset pair" in error_message:
                    logger.warning(
                        f"Symbol {symbol} not supported on {self.name}: {data['error']}"
                    )
                    self.add_to_blacklist(symbol)
                    return None
                elif "rate limit" in error_message:
                    logger.error(f"Rate limit error on {self.name}: {data['error']}")
                    return None
                else:
                    logger.error(f"Kraken API error: {data['error']}")
                    return None

            result = data["result"]
            ticker_data = list(result.values())[0]

            return CryptoPrice(
                price=Decimal(ticker_data["c"][0]),  # Last trade closed price
                volume_24h=Decimal(ticker_data["v"][1]),  # 24h volume
                # Kraken doesn't provide % change directly, would need additional calculation
                exchange=self.name,
            )
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class GateIOConnector(ExchangeConnector):
    name = "gateio"
    base_url = "https://api.gateio.ws/api/v4"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to Gate.io format
            gate_symbol = f"{symbol}_USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/spot/tickers", params={"currency_pair": gate_symbol}
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            if isinstance(data, list) and len(data) > 0:
                ticker = data[0]
                return CryptoPrice(
                    price=Decimal(ticker["last"]),
                    volume_24h=Decimal(ticker["quote_volume"]),
                    change_24h=Decimal(ticker["change_percentage"]),
                    exchange=self.name,
                )
            return None
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class CryptoCompareConnector(ExchangeConnector):
    name = "cryptocompare"
    base_url = "https://min-api.cryptocompare.com/data"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            response = await self.client.get(
                f"{self.base_url}/pricemultifull",
                params={"fsyms": symbol, "tsyms": "USD"},
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            # CryptoCompare specific error handling for unknown symbols
            if "Response" in data and data["Response"] == "Error":
                if "there is no data for the symbol" in data.get("Message", "").lower():
                    logger.warning(f"Symbol {symbol} not supported on {self.name}")
                    self.add_to_blacklist(symbol)
                    return None
                else:
                    logger.error(
                        f"CryptoCompare API error: {data.get('Message', 'Unknown error')}"
                    )
                    return None

            if "RAW" in data and symbol in data["RAW"] and "USD" in data["RAW"][symbol]:
                ticker = data["RAW"][symbol]["USD"]
                return CryptoPrice(
                    price=Decimal(str(ticker["PRICE"])),
                    volume_24h=Decimal(str(ticker["VOLUME24HOUR"])),
                    change_24h=Decimal(str(ticker["CHANGEPCT24HOUR"])),
                    exchange=self.name,
                )
            return None
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class HuobiConnector(ExchangeConnector):
    name = "huobi"
    base_url = "https://api.huobi.pro"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to Huobi format
            huobi_symbol = f"{symbol.lower()}usdt"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/market/detail/merged", params={"symbol": huobi_symbol}
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            # Huobi specific error handling
            if data["status"] != "ok":
                error_msg = data.get("err-msg", "").lower()
                if "symbol" in error_msg and (
                    "invalid" in error_msg or "not found" in error_msg
                ):
                    logger.warning(
                        f"Symbol {symbol} not supported on {self.name}: {error_msg}"
                    )
                    self.add_to_blacklist(symbol)
                    return None
                else:
                    logger.error(f"Huobi API error: {error_msg}")
                    return None

            ticker = data["tick"]

            # Get 24h stats
            stats_response = await self.client.get(
                f"{self.base_url}/market/detail", params={"symbol": huobi_symbol}
            )
            stats_data = stats_response.json()

            change_24h = None
            if stats_data["status"] == "ok" and "tick" in stats_data:
                open_price = Decimal(str(stats_data["tick"]["open"]))
                close_price = Decimal(str(ticker["close"]))
                if open_price > 0:
                    change_24h = ((close_price - open_price) / open_price) * 100

            return CryptoPrice(
                price=Decimal(str(ticker["close"])),
                volume_24h=Decimal(str(ticker["vol"])),
                change_24h=change_24h,
                exchange=self.name,
            )
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class OKXConnector(ExchangeConnector):
    name = "okx"
    base_url = "https://www.okx.com/api/v5"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to OKX format
            okx_symbol = f"{symbol}-USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/market/ticker", params={"instId": okx_symbol}
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            # OKX specific error handling
            if data["code"] != "0":
                error_msg = data.get("msg", "").lower()
                if "not found" in error_msg or "invalid" in error_msg:
                    logger.warning(
                        f"Symbol {symbol} not supported on {self.name}: {error_msg}"
                    )
                    self.add_to_blacklist(symbol)
                    return None
                elif "too many requests" in error_msg:
                    logger.error(f"Rate limit error on {self.name}: {error_msg}")
                    return None
                else:
                    logger.error(f"OKX API error: {error_msg}")
                    return None

            if len(data["data"]) > 0:
                ticker = data["data"][0]

                # Calculate 24h change
                last_price = Decimal(ticker["last"])
                open_24h = Decimal(ticker["open24h"])
                change_24h = (
                    ((last_price - open_24h) / open_24h) * 100
                    if open_24h != 0
                    else Decimal("0")
                )

                return CryptoPrice(
                    price=last_price,
                    volume_24h=Decimal(ticker["vol24h"]),
                    change_24h=change_24h,
                    exchange=self.name,
                )
            return None
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class KuCoinConnector(ExchangeConnector):
    name = "kucoin"
    base_url = "https://api.kucoin.com/api/v1"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to KuCoin format
            kucoin_symbol = f"{symbol}-USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/market/orderbook/level1",
                params={"symbol": kucoin_symbol},
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            # KuCoin specific error handling
            if data["code"] != "200000":
                error_msg = data.get("msg", "").lower()
                if "symbol" in error_msg and (
                    "not exist" in error_msg or "invalid" in error_msg
                ):
                    logger.warning(
                        f"Symbol {symbol} not supported on {self.name}: {error_msg}"
                    )
                    self.add_to_blacklist(symbol)
                    return None
                elif "too many requests" in error_msg:
                    logger.error(f"Rate limit error on {self.name}: {error_msg}")
                    return None
                else:
                    logger.error(f"KuCoin API error: {error_msg}")
                    return None

            if "data" in data:
                price_data = data["data"]

                # Get 24h stats
                stats_response = await self.client.get(
                    f"{self.base_url}/market/stats", params={"symbol": kucoin_symbol}
                )
                stats_data = stats_response.json()

                if stats_data["code"] == "200000" and "data" in stats_data:
                    stats = stats_data["data"]

                    return CryptoPrice(
                        price=Decimal(price_data["price"]),
                        volume_24h=Decimal(stats["vol"]),
                        change_24h=Decimal(stats["changeRate"])
                        * 100,  # Convert to percentage
                        exchange=self.name,
                    )
            return None
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None


class BybitConnector(ExchangeConnector):
    name = "bybit"
    base_url = "https://api.bybit.com/v5"

    async def get_ticker_price(self, symbol: str) -> Optional[CryptoPrice]:
        try:
            # Check blacklist first
            if self.check_blacklist(symbol):
                logger.debug(f"Skipping blacklisted symbol {symbol} on {self.name}")
                return None

            # Convert symbol to Bybit format
            bybit_symbol = f"{symbol}USDT"

            # Get ticker price
            response = await self.client.get(
                f"{self.base_url}/market/tickers",
                params={"category": "spot", "symbol": bybit_symbol},
            )

            try:
                data = await self.handle_response(response)
            except UnknownAssetError as e:
                logger.warning(
                    f"Symbol {symbol} not supported on {self.name}: {str(e)}"
                )
                self.add_to_blacklist(symbol)
                return None
            except RateLimitError as e:
                logger.error(f"Rate limit error on {self.name}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
                return None

            # Bybit specific error handling
            if data["retCode"] != 0:
                error_msg = data.get("retMsg", "").lower()
                if "not found" in error_msg or "invalid" in error_msg:
                    logger.warning(
                        f"Symbol {symbol} not supported on {self.name}: {error_msg}"
                    )
                    self.add_to_blacklist(symbol)
                    return None
                elif "rate limit" in error_msg:
                    logger.error(f"Rate limit error on {self.name}: {error_msg}")
                    return None
                else:
                    logger.error(f"Bybit API error: {error_msg}")
                    return None

            if "result" in data and "list" in data["result"] and data["result"]["list"]:
                ticker = data["result"]["list"][0]

                price = Decimal(ticker["lastPrice"])
                prev_price = Decimal(ticker["prevPrice24h"])
                change_24h = (
                    ((price - prev_price) / prev_price) * 100
                    if prev_price != 0
                    else Decimal("0")
                )

                return CryptoPrice(
                    price=price,
                    volume_24h=Decimal(ticker["volume24h"]),
                    change_24h=change_24h,
                    exchange=self.name,
                )
            return None
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {self.name}: {str(e)}")
            return None
