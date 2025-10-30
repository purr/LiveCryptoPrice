import json
import os
from typing import Dict, List


class BlacklistManager:
    """
    Manages a blacklist of unsupported tickers per exchange
    """

    def __init__(self, blacklist_file: str = None):
        """
        Initialize the blacklist manager

        Args:
            blacklist_file: Path to the blacklist file
        """
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # Set default blacklist file if not provided
        if blacklist_file is None:
            self.blacklist_file = os.path.join(data_dir, "ticker_blacklist.json")
        else:
            # If a file path was provided, ensure it's in the data directory
            if not os.path.dirname(blacklist_file):
                self.blacklist_file = os.path.join(data_dir, blacklist_file)
            else:
                self.blacklist_file = blacklist_file

        # Load blacklist or create empty one
        self.blacklist = self._load_blacklist()

    def _load_blacklist(self) -> Dict[str, List[str]]:
        """
        Load blacklist from file or create empty blacklist

        Returns:
            Dictionary mapping exchange names to lists of unsupported tickers
        """
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_blacklist(self):
        """Save blacklist to file"""
        with open(self.blacklist_file, "w") as f:
            json.dump(self.blacklist, f)

    def is_ticker_blacklisted(self, ticker: str, exchange: str) -> bool:
        """
        Check if a ticker is blacklisted for an exchange

        Args:
            ticker: The ticker symbol
            exchange: The exchange name

        Returns:
            True if the ticker is blacklisted for the exchange, False otherwise
        """
        if exchange not in self.blacklist:
            return False

        return ticker in self.blacklist[exchange]

    def add_to_blacklist(self, ticker: str, exchange: str):
        """
        Add a ticker to the blacklist for an exchange

        Args:
            ticker: The ticker symbol
            exchange: The exchange name
        """
        if exchange not in self.blacklist:
            self.blacklist[exchange] = []

        if ticker not in self.blacklist[exchange]:
            self.blacklist[exchange].append(ticker)
            self._save_blacklist()

    def get_blacklisted_tickers(self, exchange: str) -> List[str]:
        """
        Get all blacklisted tickers for an exchange

        Args:
            exchange: The exchange name

        Returns:
            List of blacklisted tickers
        """
        if exchange not in self.blacklist:
            return []

        return self.blacklist[exchange]

    def get_all_exchanges_for_ticker(self, ticker: str) -> List[str]:
        """
        Get all exchanges where a ticker is blacklisted

        Args:
            ticker: The ticker symbol

        Returns:
            List of exchange names
        """
        return [
            exchange
            for exchange, tickers in self.blacklist.items()
            if ticker in tickers
        ]

    def get_blacklist_stats(self) -> Dict:
        """
        Get statistics about the blacklist

        Returns:
            Dictionary with blacklist statistics
        """
        total_entries = 0
        exchanges = set()
        tickers = set()

        for exchange, ticker_list in self.blacklist.items():
            exchanges.add(exchange)
            total_entries += len(ticker_list)
            tickers.update(ticker_list)

        return {
            "total_entries": total_entries,
            "exchanges": len(exchanges),
            "tickers": len(tickers),
            "exchange_list": list(exchanges),
        }
