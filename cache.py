import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


class PriceCache:
    """Cache for cryptocurrency price data"""

    def __init__(self, cache_file: str = None, cache_duration: int = 60):
        """
        Initialize the cache

        Args:
            cache_file: Path to the cache file
            cache_duration: Cache duration in seconds
        """
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # Set default cache file if not provided
        if cache_file is None:
            cache_file = os.path.join(data_dir, "price_cache.json")
        else:
            # If a file path was provided, ensure it's in the data directory
            if not os.path.dirname(cache_file):
                cache_file = os.path.join(data_dir, cache_file)

        self.cache_file = cache_file
        self.cache_duration = cache_duration
        self.cache_data = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cache from file or create empty cache"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"last_updated": time.time(), "data": {}}
        return {"last_updated": time.time(), "data": {}}

    def _save_cache(self):
        """Save cache to file"""
        with open(self.cache_file, "w") as f:
            json.dump(self.cache_data, f)

    def get(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """
        Get cached price data for symbol and exchange if it's still fresh

        Args:
            symbol: Cryptocurrency symbol
            exchange: Exchange name

        Returns:
            Cached price data or None if not found or expired
        """
        key = f"{symbol}:{exchange}".lower()

        # Check if we have this symbol and exchange in cache
        if key not in self.cache_data["data"]:
            return None

        entry = self.cache_data["data"][key]

        # Check if cache is still valid (not expired)
        if time.time() - entry["timestamp"] > self.cache_duration:
            return None

        return entry["data"]

    def set(self, symbol: str, exchange: str, data: Dict[str, Any]):
        """
        Set price data in cache for symbol and exchange

        Args:
            symbol: Cryptocurrency symbol
            exchange: Exchange name
            data: Price data to cache
        """
        key = f"{symbol}:{exchange}".lower()

        # Update cache
        self.cache_data["data"][key] = {"timestamp": time.time(), "data": data}

        self.cache_data["last_updated"] = time.time()

        # Save to file
        self._save_cache()

    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the cache"""
        data_count = len(self.cache_data["data"])
        exchanges = set()
        symbols = set()

        for key in self.cache_data["data"].keys():
            if ":" in key:
                symbol, exchange = key.split(":")
                symbols.add(symbol.upper())
                exchanges.add(exchange)

        last_updated = datetime.fromtimestamp(self.cache_data["last_updated"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        return {
            "entries": data_count,
            "exchanges": len(exchanges),
            "symbols": len(symbols),
            "last_updated": last_updated,
        }

    @staticmethod
    def get_cache_path() -> str:
        """Get the default cache path"""
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        return os.path.join(data_dir, "price_cache.json")
