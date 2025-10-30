import asyncio
import sys
from decimal import Decimal
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher
from loguru import logger

import config
from main import AverageCryptoData, CryptoPrice, get_crypto_prices

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)

# Initialize bot
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()


def format_price_change(change: Optional[Decimal]) -> str:
    """Format price change with arrow indicator and brackets"""
    if change is None:
        return "[N/A]"  # No need to escape in HTML mode

    if change > 0:
        return f"[▲ +{change:.2f}%]"  # No need to escape in HTML mode
    elif change < 0:
        return f"[▼ {change:.2f}%]"  # No need to escape in HTML mode
    else:
        return f"[◆ {change:.2f}%]"  # No need to escape in HTML mode


def format_price_with_separators(price: Decimal) -> str:
    """Format price with thousand separators"""
    return f"{float(price):,.3f}"


def format_crypto_message(ticker: str, data: AverageCryptoData) -> str:
    """
    Format cryptocurrency data as a message for Telegram

    Args:
        ticker: The cryptocurrency ticker
        data: The cryptocurrency data

    Returns:
        Formatted message string
    """
    # Format the header with average price and change
    change_str = format_price_change(data.average_change_24h)

    # Format price with thousand separators and as code block for copying
    formatted_price = format_price_with_separators(data.average_price)
    header = f"📈 <code>${formatted_price}</code> {change_str}"

    # Format the sources section with bold header
    sources_section = "\n\n<b>Sources:</b>"

    # Sort exchange data
    sorted_exchanges = sort_exchange_data(data.exchange_data)

    # Add each exchange source
    for exchange_data in sorted_exchanges:
        exchange_change = format_price_change(exchange_data.change_24h)
        formatted_exchange_price = format_price_with_separators(exchange_data.price)
        sources_section += f"\n• {exchange_data.exchange.capitalize()}: <code>${formatted_exchange_price}</code> {exchange_change}"

    # Final message with proper spacing
    return header + " " * 50 + sources_section


def format_simple_crypto_message(ticker: str, data: AverageCryptoData) -> str:
    """
    Format cryptocurrency data as a simple message for Telegram
    Just shows ticker, price and change

    Args:
        ticker: The cryptocurrency ticker
        data: The cryptocurrency data

    Returns:
        Formatted message string
    """
    # Format price with thousand separators and as code block for copying
    formatted_price = format_price_with_separators(data.average_price)
    change_str = format_price_change(data.average_change_24h)

    return f"${ticker} <code>${formatted_price}</code> {change_str}"


def format_simple_multi_ticker_message(
    results: Dict[str, AverageCryptoData], tickers: List[str]
) -> str:
    """
    Format multiple cryptocurrencies in a single simple message

    Args:
        results: Dictionary of ticker to crypto data
        tickers: List of tickers to include in the message

    Returns:
        Formatted message string with one ticker per line
    """
    # Create a list of tuples with ticker data for sorting
    ticker_data = []

    # Collect data for tickers that exist in results
    for ticker in tickers:
        if ticker in results:
            data = results[ticker]
            ticker_data.append((ticker, data))

    # Sort tickers by:
    # 1. Ticker length (shortest first, longest last)
    # 2. Price (highest first if same length)
    sorted_tickers = sorted(
        ticker_data, key=lambda x: (len(x[0]), -float(x[1].average_price))
    )

    # Format each ticker line
    lines = []
    for ticker, data in sorted_tickers:
        formatted_price = format_price_with_separators(data.average_price)
        change_str = format_price_change(data.average_change_24h)
        lines.append(f"${ticker} <code>${formatted_price}</code> {change_str}")

    # Join all lines with newlines
    return "\n".join(lines)


def sort_exchange_data(exchange_data: Dict[str, CryptoPrice]) -> List[CryptoPrice]:
    """
    Sort exchange data according to the configuration

    Args:
        exchange_data: Dictionary of exchange name to CryptoPrice

    Returns:
        List of CryptoPrice objects sorted according to config
    """
    if not config.SORTING["enabled"]:
        return list(exchange_data.values())

    # Extract values as list
    exchange_prices = list(exchange_data.values())

    # Define sort key functions
    def get_primary_key(item: CryptoPrice):
        # If the exchange doesn't have market cap data, sort it last
        if item.volume_24h is None:
            return float("inf")  # This will make it appear last

        if config.SORTING["primary_key"] == "length":
            return len(item.exchange)
        elif config.SORTING["primary_key"] == "price":
            return float(item.price)
        return 0

    def get_secondary_key(item: CryptoPrice):
        if config.SORTING["secondary_key"] == "length":
            return len(item.exchange)
        elif config.SORTING["secondary_key"] == "price":
            return float(item.price)
        return 0

    # Determine sort directions
    primary_reverse = config.SORTING["order"][config.SORTING["primary_key"]] == "desc"
    secondary_reverse = (
        config.SORTING["order"][config.SORTING["secondary_key"]] == "desc"
    )

    # Sort with primary key first, then secondary key
    return sorted(
        exchange_prices,
        key=lambda x: (get_primary_key(x), get_secondary_key(x)),
        reverse=(primary_reverse, secondary_reverse),
    )


async def fetch_and_send_updates():
    """Fetch cryptocurrency data and send updates to channels"""
    try:
        # Collect all unique tickers from channel configurations
        all_tickers = set()
        for channel in config.CHANNELS:
            all_tickers.update(channel["tickers"])

        # Convert to list and fetch data
        tickers_list = list(all_tickers)
        logger.info(f"Fetching data for {', '.join(tickers_list)}...")

        # Get price data for all tickers
        results = await get_crypto_prices(
            tickers_list, use_cache=True, cache_duration=60
        )

        # Process each channel
        for channel in config.CHANNELS:
            channel_id = channel["channel_id"]
            tickers = channel["tickers"]
            channel_format = channel.get(
                "format", "detailed"
            )  # Default to detailed format

            if channel_format == "simple" and len(tickers) > 1:
                # For simple format with multiple tickers, send a single message with all tickers
                message = format_simple_multi_ticker_message(results, tickers)

                # Only send if we have data for at least one ticker
                if message:
                    try:
                        await bot.send_message(
                            chat_id=channel_id,
                            text=message,
                            parse_mode="HTML",  # Use HTML parsing
                        )
                        logger.info(f"Sent multi-ticker update to channel {channel_id}")
                    except Exception as e:
                        logger.error(
                            f"Error sending multi-ticker message to channel {channel_id}: {str(e)}"
                        )
                        # Try without HTML formatting
                        try:
                            simple_message = (
                                message.replace("<code>", "")
                                .replace("</code>", "")
                                .replace("<b>", "")
                                .replace("</b>", "")
                            )
                            await bot.send_message(
                                chat_id=channel_id, text=simple_message
                            )
                            logger.info(
                                f"Sent multi-ticker update without formatting to channel {channel_id}"
                            )
                        except Exception as retry_error:
                            logger.error(f"Retry failed: {str(retry_error)}")
            else:
                # For detailed format or simple format with single ticker, send separate message for each ticker
                for ticker in tickers:
                    if ticker in results:
                        data = results[ticker]

                        # Format message based on channel format
                        if channel_format == "simple":
                            message = format_simple_crypto_message(ticker, data)
                        else:
                            message = format_crypto_message(ticker, data)

                        # Send message to the channel
                        try:
                            # Send message with HTML parsing enabled for bold and code blocks
                            await bot.send_message(
                                chat_id=channel_id,
                                text=message,
                                parse_mode="HTML",  # Use HTML parsing
                            )
                            logger.info(f"Sent {ticker} update to channel {channel_id}")
                        except Exception as e:
                            logger.error(
                                f"Error sending message to channel {channel_id}: {str(e)}"
                            )

                            # If HTML parsing fails, try sending without formatting
                            try:
                                logger.info(
                                    f"Retrying without HTML for {ticker} to channel {channel_id}"
                                )
                                simple_message = (
                                    message.replace("<code>", "")
                                    .replace("</code>", "")
                                    .replace("<b>", "")
                                    .replace("</b>", "")
                                )
                                await bot.send_message(
                                    chat_id=channel_id, text=simple_message
                                )
                                logger.info(
                                    f"Sent {ticker} update without formatting to channel {channel_id}"
                                )
                            except Exception as retry_error:
                                logger.error(f"Retry failed: {str(retry_error)}")
                    else:
                        logger.warning(f"No data found for ticker {ticker}")

    except Exception as e:
        logger.error(f"Error in update cycle: {str(e)}")


async def scheduled_updates():
    """Run scheduled updates every UPDATE_INTERVAL seconds"""
    while True:
        try:
            await fetch_and_send_updates()
        except Exception as e:
            logger.error(f"Error in update cycle: {str(e)}")

        # Wait for next update
        logger.info(
            f"Sleeping for {config.UPDATE_INTERVAL} seconds until next update..."
        )
        await asyncio.sleep(config.UPDATE_INTERVAL)


async def main():
    """Main entry point"""
    logger.info("Starting crypto price bot...")

    # Start the scheduled updates as the only task
    update_task = asyncio.create_task(scheduled_updates())

    try:
        # Keep the bot running until interrupted
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        # If the main task is cancelled, also cancel the update task
        update_task.cancel()
        await update_task
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        update_task.cancel()
        await update_task
    finally:
        logger.info("Bot shutting down")


if __name__ == "__main__":
    asyncio.run(main())
