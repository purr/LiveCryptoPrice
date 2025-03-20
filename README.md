# Live Crypto Price Telegram Bot

A Telegram bot that fetches cryptocurrency prices from multiple sources and sends updates to configured Telegram channels.

## Features

- Fetches cryptocurrency prices from multiple sources:
  - CoinGecko
  - CryptoCompare
  - Binance
  - Kraken
  - Huobi
- Calculates average price across all sources
- Sends formatted updates to multiple Telegram channels
- Configurable update intervals
- Handles API rate limits and errors
- Supports different tickers for different channels
- Utilizes aiogram 3.x for Telegram integration

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Create your Telegram Bot**

   - Talk to [@BotFather](https://t.me/BotFather) on Telegram
   - Create a new bot with `/newbot` command
   - Copy the API token provided

3. **Configure environment variables**

   Create a `.env` file in the project root directory:

   ```
   BOT_TOKEN=your_telegram_bot_token_here
   ```

4. **Configure the bot**

   Edit `config.json` to set up your channels and preferences:

   ```json
   {
     "update_interval": 300,
     "cache_time": 5,
     "channels": [
       {
         "channel_id": "-1001234567890",
         "tickers": ["BTC", "ETH", "SOL", "TON"]
       },
       {
         "channel_id": "-1009876543210",
         "tickers": ["BTC", "TON"]
       }
     ],
     "show_individual_sources": true,
     "retry_interval": 60,
     "timeout": 10
   }
   ```

5. **Add the bot to your channels**

   - Add your bot as an administrator to the channels
   - Make sure it has permission to post messages

## Running the Bot

```bash
python telegram_bot.py
```

## Configuration Options

- `update_interval`: Time in seconds between updates (default: 300)
- `cache_time`: Time in seconds to cache API responses (default: 5)
- `channels`: List of channel configurations
  - `channel_id`: Telegram channel ID (must start with `-100` for public channels)
  - `tickers`: List of cryptocurrency tickers to track for this channel
- `show_individual_sources`: Whether to show individual sources in the message (default: true)
- `retry_interval`: Time in seconds to wait before retrying after an error (default: 60)
- `timeout`: HTTP request timeout in seconds (default: 10)

## Supported Cryptocurrencies

The bot currently has built-in support for the following cryptocurrencies:

- BTC (Bitcoin)
- ETH (Ethereum)
- SOL (Solana)
- TON (The Open Network)
- DOGE (Dogecoin)
- XRP (Ripple)
- ADA (Cardano)
- DOT (Polkadot)
- AVAX (Avalanche)
- LINK (Chainlink)

To add support for additional cryptocurrencies, edit the ticker maps in the rate functions.

## Troubleshooting

If you encounter errors related to imports or missing modules:

- Make sure you have installed all dependencies: `pip install -r requirements.txt`
- Ensure you're using aiogram 3.x, as this project uses the new exception handling structure

## License

MIT
