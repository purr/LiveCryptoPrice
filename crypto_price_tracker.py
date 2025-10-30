import argparse
import asyncio
import os
import sys
from collections import defaultdict
from typing import List

from loguru import logger

from cache import PriceCache
from main import get_crypto_prices

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


async def get_average_crypto_prices(
    symbols: List[str],
    debug: bool = False,
    no_cache: bool = False,
    cache_duration: int = 60,
):
    """
    Get average crypto prices from multiple exchanges.

    Args:
        symbols: List of cryptocurrency ticker symbols (e.g. ['BTC', 'ETH', 'SOL'])
        debug: If True, show detailed information about exchange support
        no_cache: If True, don't use cache
        cache_duration: Cache duration in seconds
    """
    if not symbols:
        print("Please provide at least one cryptocurrency symbol")
        return

    print(f"Fetching data for {', '.join(symbols)}...")

    # Display cache info if using cache
    if not no_cache:
        cache_file = PriceCache.get_cache_path()
        if os.path.exists(cache_file):
            cache = PriceCache(cache_duration=cache_duration)
            cache_info = cache.get_cache_info()
            print(
                f"Using cache: {cache_info['entries']} entries for {cache_info['symbols']} symbols across {cache_info['exchanges']} exchanges"
            )
            print(
                f"Last updated: {cache_info['last_updated']}, Cache duration: {cache_duration}s"
            )

    results = await get_crypto_prices(
        symbols, use_cache=not no_cache, cache_duration=cache_duration
    )

    if debug:
        print("\n--- DEBUG MODE: EXCHANGE SUPPORT ---")
        print("{:<6} {:<50}".format("Symbol", "Supported by"))
        print("-" * 60)

        # For summary statistics
        all_exchanges = {
            "binance",
            "kraken",
            "gateio",
            "cryptocompare",
            "huobi",
            "okx",
            "kucoin",
            "bybit",
        }
        exchange_support_count = defaultdict(int)
        coin_support_summary = {}

        for symbol, data in results.items():
            exchanges = list(data.exchange_data.keys())
            support_info = f"{len(exchanges)}/8 exchanges: {', '.join(exchanges)}"
            print("{:<6} {:<50}".format(symbol, support_info))

            # Track which exchanges support this coin
            for exchange in exchanges:
                exchange_support_count[exchange] += 1

            # Store support percentage for this coin
            coin_support_summary[symbol] = (len(exchanges) / len(all_exchanges)) * 100

            # Show which exchanges don't support this coin
            unsupported = all_exchanges - set(exchanges)
            if unsupported:
                print(
                    "{:<6} {:<50}".format(
                        "", f"Not supported by: {', '.join(unsupported)}"
                    )
                )
            print()

        # Show exchange coverage
        print("--- EXCHANGE COVERAGE SUMMARY ---")
        print("{:<15} {:<10} {:<10}".format("Exchange", "Coins", "Coverage %"))
        print("-" * 40)

        for exchange in sorted(all_exchanges):
            count = exchange_support_count[exchange]
            coverage = (count / len(symbols)) * 100
            print("{:<15} {:<10} {:<10.2f}%".format(exchange, count, coverage))

        # Show coin coverage
        print("\n--- COIN SUPPORT SUMMARY ---")
        print("{:<6} {:<10}".format("Symbol", "Support %"))
        print("-" * 20)

        for symbol, coverage in sorted(
            coin_support_summary.items(), key=lambda x: x[1]
        ):
            print("{:<6} {:<10.2f}%".format(symbol, coverage))

        # Show error type counts if available
        print("\n--- ERROR TYPE SUMMARY ---")
        for symbol, data in results.items():
            # Count is implied by what's missing from exchange_data
            all_exchanges_set = set(all_exchanges)
            supported_exchanges = set(data.exchange_data.keys())
            missing_exchanges = all_exchanges_set - supported_exchanges

            # We'd need to collect error types from the main module to properly fill this
            # For now we just show the summary of missing exchanges
            print(
                f"{symbol}: Missing from {len(missing_exchanges)} exchanges: {', '.join(missing_exchanges) if missing_exchanges else 'None'}"
            )

        print("--- END DEBUG MODE ---\n")

    print(
        "\n{:<6} {:<14} {:<20} {:<12}".format(
            "Symbol", "Price (USD)", "24h Volume (USD)", "24h Change"
        )
    )
    print("-" * 55)

    for symbol, data in results.items():
        price = f"${data.average_price:.2f}"

        if data.average_volume_24h:
            volume = f"${data.average_volume_24h:.2f}"
        else:
            volume = "N/A"

        if data.average_change_24h:
            change = f"{data.average_change_24h:.2f}%"
            if data.average_change_24h > 0:
                change = f"+{change}"
        else:
            change = "N/A"

        print("{:<6} {:<14} {:<20} {:<12}".format(symbol, price, volume, change))

        # Show which exchanges were used
        exchanges = list(data.exchange_data.keys())
        print(f"  Data from {len(exchanges)} exchanges: {', '.join(exchanges)}\n")


async def main():
    parser = argparse.ArgumentParser(
        description="Fetch cryptocurrency prices from multiple exchanges"
    )
    parser.add_argument(
        "symbols", nargs="*", help="Cryptocurrency symbols to fetch (e.g. BTC ETH SOL)"
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode to check exchange support",
    )
    parser.add_argument(
        "--no-cache",
        "-n",
        action="store_true",
        help="Disable cache and fetch fresh data",
    )
    parser.add_argument(
        "--cache-duration",
        "-c",
        type=int,
        default=60,
        help="Cache duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear the cache before running"
    )
    args = parser.parse_args()

    # Handle cache clearing if requested
    if args.clear_cache:
        cache_file = PriceCache.get_cache_path()
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"Cache cleared: {cache_file} deleted")

    symbols = args.symbols

    if not symbols:
        # If no arguments, ask for input
        symbols_input = input(
            "Enter cryptocurrency symbols separated by space (e.g., BTC ETH SOL): "
        )
        symbols = [symbol.upper() for symbol in symbols_input.split()]
    else:
        symbols = [symbol.upper() for symbol in symbols]

    await get_average_crypto_prices(
        symbols,
        debug=args.debug,
        no_cache=args.no_cache,
        cache_duration=args.cache_duration,
    )


if __name__ == "__main__":
    asyncio.run(main())
