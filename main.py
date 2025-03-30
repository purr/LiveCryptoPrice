import os
import json
import time
import asyncio
import pathlib
from typing import Any, Dict, List, Optional

"""
Live Crypto Price Bot
Version: 1.3.0
- Added concurrent processing of channels using async tasks
- Improved performance with parallel ticker processing
- Optimized code structure by reducing redundancy
- Added tracking for unsupported exchange-ticker pairs
- Implemented skipping of known unsupported pairs for better performance
- Reverted to sequential channel updates for stability
- Enhanced cache usage for better performance
"""

from dotenv import load_dotenv
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramRetryAfter,
    TelegramForbiddenError,
)
from aiogram.client.default import DefaultBotProperties

from config import (
    SORTING,
    CHANNELS,
    RETRY_INTERVAL,
    UPDATE_INTERVAL,
    SHOW_INDIVIDUAL_SOURCES,
)
from utils.rates import format_price, get_cached_price, get_crypto_price
from utils.logger import logger

# Data directory setup
DATA_DIR = "data"
PRICE_HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")


def ensure_data_directory():
    """Create data directory if it doesn't exist."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info(f"Created data directory: {DATA_DIR}")


def load_price_history():
    """Load price history from JSON file or create a new one if it doesn't exist."""
    ensure_data_directory()
    history_path = pathlib.Path(PRICE_HISTORY_FILE)
    if history_path.exists():
        try:
            with open(PRICE_HISTORY_FILE, "r") as history_file:
                return json.load(history_file)
        except Exception as e:
            logger.error(f"Error loading price history: {e}")
            return {}
    else:
        logger.info("Price history file not found, creating new history.")
        save_price_history({})  # Create empty file
        return {}


def save_price_history(history):
    """Save price history to JSON file."""
    ensure_data_directory()
    try:
        with open(PRICE_HISTORY_FILE, "w") as history_file:
            json.dump(history, history_file, indent=2)
    except Exception as e:
        logger.error(f"Error saving price history: {e}")


# Initialize price history
price_history = load_price_history()

# Load environment variables from .env file
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

# Initialize bot with new syntax for aiogram 3.7.0+
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

logger.debug(f"Loaded configuration with update interval: {UPDATE_INTERVAL}")


async def check_channel_access(channel_id: str) -> bool:
    """Check if the bot has access to a channel and can post messages."""
    logger.debug(f"Checking access to channel {channel_id}")
    try:
        chat = await bot.get_chat(channel_id)
        logger.debug(f"Found chat: {chat.title}")

        # Try sending a message to check if bot has permission to post
        bot_member = await bot.get_chat_member(chat.id, bot.id)

        # Check if bot has permission to send messages
        if (
            hasattr(bot_member, "can_post_messages")
            and not bot_member.can_post_messages
        ):
            logger.warning(f"Bot doesn't have post permission in {channel_id}")
            return False

        logger.debug(f"Bot has access to channel {chat.title}")
        return True
    except TelegramAPIError as e:
        if "chat not found" in str(e).lower():
            logger.error(f"Channel {channel_id} not found")
        elif "bot is not a member" in str(e).lower() or "forbidden" in str(e).lower():
            logger.error(f"Bot is not a member of channel {channel_id}")
        else:
            logger.error(f"API error for channel {channel_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking channel {channel_id}: {e}")
        return False


async def fetch_price_data(ticker: str) -> Optional[Dict[str, Any]]:
    """Asynchronously fetch price data for a ticker, using cache when available."""
    try:
        # First, try to get cached data
        cached_data = get_cached_price(ticker)
        if cached_data:
            logger.debug(f"Using cached data for {ticker}")
            return cached_data

        # If no cached data is available, fetch from external APIs
        logger.debug(f"No cached data for {ticker}, fetching from APIs")
        return await asyncio.to_thread(get_crypto_price, ticker)
    except Exception as e:
        logger.error(f"Error fetching price for {ticker}: {e}")
        return None


def format_market_change(change):
    """Format market change with up/down arrows as requested."""
    if change is None:
        return f"[N/A]"

    # Format with 2 decimal places and proper sign
    if change > 0:
        return f"[▲ +{change:.2f}%]"
    elif change < 0:
        return f"[▼ {change:.2f}%]"
    else:
        return f"[— {change:.2f}%]"


async def process_ticker_data(ticker: str) -> Optional[Dict[str, Any]]:
    """Process data for a single ticker, to be used concurrently."""
    try:
        data = await fetch_price_data(ticker)
        if not data or data.get("average_price") is None:
            logger.warning(f"No price data for {ticker}")
            return None

        # Get current price
        current_price = data["average_price"]

        # Get 24h change percentage and format it
        change_24h = data.get("average_change_24h")
        change_24h_str = (
            format_market_change(change_24h) if change_24h is not None else "N/A"
        )

        # Get price change indicator based on last recorded price
        price_indicator = "—"
        price_changed = "none"

        if ticker in price_history:
            prev_price = price_history[ticker]
            if current_price > prev_price:
                price_indicator = "📈"  # Green up arrow for price increase
                price_changed = "up"
            elif current_price < prev_price:
                price_indicator = "📉"  # Red down arrow for price decrease
                price_changed = "down"

        # Update price history for next comparison
        price_history[ticker] = current_price
        save_price_history(price_history)

        # Return ticker data for sorting and formatting
        return {
            "ticker": ticker,
            "length": len(ticker),
            "price": current_price,
            "price_str": format_price(current_price),
            "change_str": change_24h_str,
            "price_indicator": price_indicator,
            "price_changed": price_changed,
            "raw_data": data,
            "active_sources": data.get("active_sources", 0),
            "skipped_sources": data.get("skipped_sources", 0),
        }
    except Exception as e:
        logger.error(f"Error processing ticker {ticker}: {e}")
        return None


async def create_consolidated_price_message(tickers: List[str]) -> Optional[str]:
    """Create a single message with price information for multiple tickers."""
    logger.debug(f"Creating consolidated price info for {tickers}")
    try:
        # Process each ticker sequentially instead of concurrently
        ticker_data = []
        for ticker in tickers:
            data = await process_ticker_data(ticker)
            if data:
                ticker_data.append(data)
            # Small delay between ticker requests to avoid overwhelming APIs
            await asyncio.sleep(0.5)

        if not ticker_data:
            return "❌ Unable to fetch prices for any tickers"

        # Apply sorting based on configuration
        if SORTING.get("enabled", True):
            primary_key = SORTING.get("primary_key", "length")
            secondary_key = SORTING.get("secondary_key", "price")
            order = SORTING.get("order", {"length": "asc", "price": "desc"})

            def sort_key(x):
                primary_value = x[primary_key]
                secondary_value = x[secondary_key]

                # Apply ordering direction
                if order.get(primary_key) == "desc":
                    primary_value = (
                        -primary_value
                        if isinstance(primary_value, (int, float))
                        else primary_value
                    )
                if order.get(secondary_key) == "desc":
                    secondary_value = (
                        -secondary_value
                        if isinstance(secondary_value, (int, float))
                        else secondary_value
                    )

                return (primary_value, secondary_value)

            ticker_data.sort(key=sort_key)

        # Format messages
        message_parts = [
            f"${item['ticker']} <code>{item['price_str']}</code> {item['change_str']}"
            for item in ticker_data
        ]

        return "\n".join(message_parts)
    except Exception as e:
        logger.error(f"Error creating consolidated message: {e}")
        return None


async def send_update_to_channel(channel_id: str, tickers: List[str]) -> bool:
    """Send crypto price updates to a specific channel."""
    logger.debug(f"Sending updates for {tickers} to {channel_id}")
    try:
        message = None
        if len(tickers) == 1:
            # For single ticker, create detailed message
            ticker = tickers[0]
            ticker_data = await process_ticker_data(ticker)
            if ticker_data:
                message_parts = []
                # Get price change indicator based on last recorded price
                price_indicator = ticker_data["price_indicator"]

                # Main header with ticker and price change indicator
                message_parts.append(
                    f"{price_indicator} <code>{ticker_data['price_str']}</code> {ticker_data['change_str']}"
                )

                # Add spacing
                message_parts.append(f"{' ' * 25}")

                # Add source count information
                active = ticker_data.get("active_sources", 0)
                skipped = ticker_data.get("skipped_sources", 0)

                logger.debug(f"Used sources: {active}")
                logger.debug(f"Skipped sources: {skipped}")

                if (
                    SHOW_INDIVIDUAL_SOURCES
                    and ticker_data["raw_data"]
                    and ticker_data["raw_data"].get("sources")
                ):
                    message_parts.append(f"<b>Sources:</b>")
                    for source, source_data in ticker_data["raw_data"][
                        "sources"
                    ].items():
                        price = source_data["price"]
                        change = source_data.get("change_24h")
                        change_str = (
                            format_market_change(change)
                            if change is not None
                            else "N/A"
                        )
                        message_parts.append(
                            f"• {source}: <code>{format_price(price)}</code> {change_str}"
                        )

                message = "\n".join(message_parts)
        else:
            # For multiple tickers, use consolidated message
            message = await create_consolidated_price_message(tickers)

        if message:
            logger.debug(f"Sending update to {channel_id}")
            await bot.send_message(channel_id, message)
            logger.debug(f"Sent update to {channel_id}")
            # Small delay to avoid hitting rate limits
            await asyncio.sleep(0.5)
            return True
        return False
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limited. Retry after {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        return False
    except TelegramForbiddenError:
        logger.error(f"Bot blocked by channel {channel_id}")
        return False
    except TelegramAPIError as e:
        logger.error(f"Telegram API Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error updating channel {channel_id}: {e}")
        return False


async def update_channels() -> None:
    """Send updates to configured channels sequentially."""
    logger.info("Starting channel updates...")

    for channel_config in CHANNELS:
        channel_id = channel_config.get("channel_id")
        tickers = channel_config.get("tickers", [])

        if not channel_id:
            logger.warning("Channel ID not specified in config")
            continue

        # Process each channel sequentially
        try:
            # Check if bot has access to the channel
            logger.debug(f"Checking access to channel {channel_id}")
            has_access = await check_channel_access(channel_id)
            if not has_access:
                logger.warning(f"No access to channel {channel_id}")
                continue

            logger.info(f"Updating channel {channel_id} with {', '.join(tickers)}")
            success = await send_update_to_channel(channel_id, tickers)
            if not success:
                logger.warning(f"Failed to update channel {channel_id}")

            # Add a small delay between channel updates
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error updating channel {channel_id}: {e}")

    logger.info("All channel updates completed")


async def display_status():
    """Display cache and unsupported pairs status information."""
    try:
        # Get cache information
        from utils.rates import price_cache, unsupported_pairs

        # Count cached items and calculate average age
        cache_count = len(price_cache)
        cache_age = 0
        current_time = time.time()

        if cache_count > 0:
            total_age = sum(
                current_time - timestamp for timestamp, _ in price_cache.values()
            )
            cache_age = total_age / cache_count

        # Count unsupported pairs
        unsupported_count = sum(len(pairs) for pairs in unsupported_pairs.values())
        exchange_count = len(unsupported_pairs)

        # Display information
        logger.info(f"Cache status: {cache_count} items, avg age: {cache_age:.1f}s")
        logger.info(
            f"Unsupported pairs: {unsupported_count} across {exchange_count} exchanges"
        )
    except Exception as e:
        logger.error(f"Error displaying status: {e}")


async def main() -> None:
    """Main function to run the bot."""
    logger.info("=" * 40)
    logger.info("Starting crypto price update bot")
    logger.info("=" * 40)

    # Ensure data directory exists
    ensure_data_directory()

    # Get bot info
    bot_info = await bot.get_me()
    logger.info(f"Bot: @{bot_info.username} (ID: {bot_info.id})")

    update_count = 0

    while True:
        try:
            # Add separator line between update cycles
            logger.info("-" * 40)

            # Display status information
            await display_status()

            start_time = time.time()
            await update_channels()
            end_time = time.time()

            update_count += 1
            duration = end_time - start_time

            logger.info(f"Update #{update_count} completed in {duration:.2f} seconds")
            logger.info(f"Next update in {UPDATE_INTERVAL} seconds")

            await asyncio.sleep(UPDATE_INTERVAL)
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.info(f"Retrying in {RETRY_INTERVAL} seconds")
            await asyncio.sleep(RETRY_INTERVAL)


if __name__ == "__main__":
    # Run the bot
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        loop.close()
