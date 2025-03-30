# Live Crypto Price Telegram Bot

A Telegram bot that fetches cryptocurrency prices from multiple sources and sends updates to configured Telegram channels.

## Features

- Fetches cryptocurrency prices from multiple sources:
  - CoinGecko
  - CryptoCompare
  - Binance
  - Kraken
  - Gate•io
  - Huobi
  - OKX
  - KuCoin
  - Bybit
  - FX Rates API
- Calculates average price across all sources
- Sends formatted updates to multiple Telegram channels
- Configurable update intervals
- Handles API rate limits and errors
- Supports different tickers for different channels
- Utilizes aiogram 3.x for Telegram integration
- Asynchronous price fetching for improved performance
- Persistent data storage in dedicated data directory
- Smart request management with proper rate limit handling

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

   Edit `config.py` to set up your channels and preferences.

5. **Add the bot to your channels**

   - Add your bot as an administrator to the channels
   - Make sure it has permission to post messages

6. **Migrate data (if upgrading)**

   If you're upgrading from a previous version, run the migration script to move your data to the new directory structure:

   ```bash
   python migrate_data.py
   ```

## Running the Bot

```bash
python main.py
```

## Configuration Options

The configuration options are set in `config.py`:

- `UPDATE_INTERVAL`: Time in seconds between updates (default: 120)
- `CHANNELS`: List of channel configurations
  - `channel_id`: Telegram channel ID (must start with `-100` for public channels)
  - `tickers`: List of cryptocurrency tickers to track for this channel
- `SHOW_INDIVIDUAL_SOURCES`: Whether to show individual sources in the message (default: true)
- `RETRY_INTERVAL`: Time in seconds to wait before retrying after an error (default: 60)
- `TIMEOUT`: HTTP request timeout in seconds (default: 10)
- `CACHE_DURATION`: Time in seconds to cache API responses (default: 60)
- `DATA_DIR`: Directory for storing data files (default: "data")
- `SORTING`: Configuration for sorting multi-ticker listings

## Exchange Support

The bot aggregates cryptocurrency prices from 10 different exchanges without requiring any API keys:

1. **CoinGecko** - Popular cryptocurrency data aggregator
2. **CryptoCompare** - Cryptocurrency data provider
3. **Binance** - One of the largest crypto exchanges by volume
4. **Kraken** - Established exchange with good reliability
5. **Gate•io** - Global exchange with wide variety of assets
6. **Huobi** - Major Asian cryptocurrency exchange
7. **OKX** - Large global exchange (formerly OKEx)
8. **KuCoin** - Popular exchange with many altcoins
9. **Bybit** - Fast-growing derivatives and spot exchange
10. **FX Rates API** - Foreign exchange rates API with cryptocurrency support

All of these exchanges offer public API endpoints that don't require authentication for basic price data, making the bot simple to set up without needing to create accounts or generate API keys.

## Request Management

The bot includes a sophisticated request management system with the following features:

- Smart handling of API rate limits (HTTP 429 responses)
- Domain-specific rate limit tracking
- Automatic retry-after handling based on API responses
- No fallback to cached data when rate limited to ensure fresh data
- Error reporting for debugging

When a rate limit is encountered for a specific API domain, the bot will:

1. Mark that domain as rate-limited
2. Skip sending requests to that domain until the rate limit expires
3. Continue fetching data from other available sources

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
- LTC (Litecoin)
- VET (VeChain)
- TRX (Tron)
- XMR (Monero)
- BNB (Binance Coin)
- NOT (Not Financial Advice)
- MAJOR (Major Protocol)

To add support for additional cryptocurrencies, edit the ticker maps in the rate functions in `utils/rates.py`.

## Data Storage

All persistent data is stored in the `data` directory:

- `price_history.json`: History of prices for change indicators
- `markets_cache.json`: Cached market data

## Troubleshooting

If you encounter errors related to imports or missing modules:

- Make sure you have installed all dependencies: `pip install -r requirements.txt`
- Ensure you're using aiogram 3.x, as this project uses the new exception handling structure
- Verify that the data directory exists and is writable

## License

MIT
