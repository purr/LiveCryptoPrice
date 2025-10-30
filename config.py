"""Configuration settings for the Live Crypto Price Bot."""

# Data directory
DATA_DIR = "data"

# Update interval in seconds
UPDATE_INTERVAL = 120

# Channel configurations
CHANNELS = [
    {"channel_id": "-1002320914547", "tickers": ["BTC"]},
    {"channel_id": "-1002514045234", "tickers": ["ETH"]},
    {"channel_id": "-1002609883021", "tickers": ["XMR"]},
    {"channel_id": "-1002283363146", "tickers": ["XRP"]},
    {"channel_id": "-1002367600542", "tickers": ["TON"]},
    {"channel_id": "-1002646484589", "tickers": ["SOL"]},
    {"channel_id": "-1002570233511", "tickers": ["BNB"]},
    {
        "channel_id": "-1002591839246",
        "tickers": [
            "BTC",
            "TON",
            "NOT",
            "MAJOR",
            "SOL",
            "XRP",
            "ETH",
            "BNB",
            "ADA",
            "DOT",
            "LTC",
            "LINK",
            "VET",
            "TRX",
            "XMR",
        ],
    },
]

# Display settings
SHOW_INDIVIDUAL_SOURCES = True

# Timing settings
RETRY_INTERVAL = 60  # seconds
TIMEOUT = 10  # seconds
CACHE_DURATION = 60  # seconds
MAX_PROXY_RETRIES = 3  # maximum number of proxy retries

# Sorting configuration
SORTING = {
    "enabled": True,
    "primary_key": "length",
    "secondary_key": "price",
    "order": {"length": "asc", "price": "desc"},
}
