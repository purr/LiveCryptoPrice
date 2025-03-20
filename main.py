import os
import sys
import json
import asyncio
import pathlib
from typing import List, Optional

from dotenv import load_dotenv
from loguru import logger
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramRetryAfter,
    TelegramForbiddenError,
)
from aiogram.client.default import DefaultBotProperties

from rates import format_price, get_crypto_price, format_percent_change

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

# Load price history or create it if it doesn't exist
PRICE_HISTORY_FILE = "price_history.json"


def load_price_history():
    """Load price history from JSON file or create a new one if it doesn't exist."""
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
        return {}


def save_price_history(history):
    """Save price history to JSON file."""
    try:
        with open(PRICE_HISTORY_FILE, "w") as history_file:
            json.dump(history, history_file, indent=2)
        logger.debug("Price history saved successfully")
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

# Load configuration
with open("config.json", "r") as config_file:
    config = json.load(config_file)
    logger.debug(f"Loaded configuration: {config}")


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


async def create_price_message(ticker: str) -> Optional[str]:
    """Create a message with the price information for a ticker."""
    logger.debug(f"Creating price info for {ticker}")
    try:
        data = get_crypto_price(ticker)
        logger.debug(f"Got data for {ticker}")

        if not data or data.get("average_price") is None:
            logger.warning(f"No price data for {ticker}")
            return f"❌ Unable to fetch {ticker} price from any source"

        # Get current price
        current_price = data["average_price"]

        # Get 24h change percentage and format it
        change_24h = data.get("average_change_24h")
        change_24h_str = (
            format_percent_change(change_24h) if change_24h is not None else "N/A"
        )

        # Debug all source changes
        logger.debug(f"24h changes for {ticker}:")
        for source, source_data in data["sources"].items():
            change = source_data.get("change_24h")
            if change is not None:
                logger.debug(f"  - {source}: {format_percent_change(change)}")
            else:
                logger.debug(f"  - {source}: N/A")

        if change_24h is not None:
            logger.debug(
                f"Average 24h change for {ticker}: {format_percent_change(change_24h)}"
            )

        # Get price change indicator based on last recorded price
        price_indicator = ""
        if ticker in price_history:
            prev_price = price_history[ticker]
            if current_price > prev_price:
                price_indicator = "📈︎"  # Green up arrow for price increase
            elif current_price < prev_price:
                price_indicator = "📉︎"  # Red down arrow for price decrease
            else:
                price_indicator = "🗠︎"  # White horizontal arrow for no change

        # Update price history for next comparison
        price_history[ticker] = current_price
        save_price_history(price_history)

        message_parts = []

        # Main header with ticker and price change indicator
        message_parts.append(
            f"{price_indicator} <code>{format_price(current_price)}</code> [{change_24h_str}]"
        )

        # Add 10 spaces dynamically
        message_parts.append(f"{' ' * 25}")

        # Individual sources if configured to show them
        if config.get("show_individual_sources", True) and data["sources"]:
            message_parts.append("<b>Sources:</b>")
            for source, source_data in data["sources"].items():
                price = source_data["price"]
                change = source_data.get("change_24h")
                change_str = (
                    format_percent_change(change) if change is not None else "N/A"
                )
                message_parts.append(
                    f"• {source}: <code>{format_price(price)}</code> [{change_str}]"
                )

        final_message = "\n".join(message_parts)
        logger.debug(f"Prepared {ticker} message")
        return final_message
    except Exception as e:
        logger.error(f"Error creating message for {ticker}: {e}")
        return None


async def send_update_to_channel(channel_id: str, tickers: List[str]) -> bool:
    """Send crypto price updates to a specific channel."""
    logger.debug(f"Sending updates for {tickers} to {channel_id}")
    try:
        for ticker in tickers:
            message = await create_price_message(ticker)
            if message:
                logger.debug(f"Sending {ticker} update to {channel_id}")
                await bot.send_message(channel_id, message)
                logger.debug(f"Sent {ticker} update to {channel_id}")
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.5)
        return True
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
    """Send updates to all configured channels."""
    logger.info("Starting channel updates...")

    for channel_config in config.get("channels", []):
        channel_id = channel_config.get("channel_id")
        tickers = channel_config.get("tickers", [])

        if not channel_id:
            logger.warning("Channel ID not specified in config")
            continue

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

    logger.info("All channel updates completed")


async def main() -> None:
    """Main function to run the bot."""
    logger.info("=" * 40)
    logger.info("Starting crypto price update bot")
    logger.info("=" * 40)

    print("=" * 40)
    print("CRYPTOCURRENCY PRICE UPDATE BOT")
    print("=" * 40)
    print("Bot is starting...")

    # Get bot info
    bot_info = await bot.get_me()
    logger.info(f"Bot: @{bot_info.username} (ID: {bot_info.id})")
    print(f"Bot: @{bot_info.username} (ID: {bot_info.id})")

    update_interval = config.get("update_interval", 300)  # Default: 5 minutes
    retry_interval = config.get("retry_interval", 60)  # Default: 1 minute

    print(f"Update interval: {update_interval} seconds")
    print(f"Configured channels: {len(config.get('channels', []))}")
    print("Bot is running. Press Ctrl+C to stop.")
    print("=" * 40)

    while True:
        try:
            await update_channels()
            logger.info(f"Next update in {update_interval} seconds")
            print(f"Updates sent! Next update in {update_interval} seconds...")
            await asyncio.sleep(update_interval)
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.info(f"Retrying in {retry_interval} seconds")
            print(f"Error occurred: {e}")
            print(f"Retrying in {retry_interval} seconds...")
            await asyncio.sleep(retry_interval)


if __name__ == "__main__":
    # Run the bot
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\nBot stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        print(f"\nFatal error: {e}")
    finally:
        loop.close()
        print("Bot stopped. Goodbye!")
