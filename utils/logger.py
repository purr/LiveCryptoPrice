import sys

from loguru import logger

# Remove default handler
logger.remove()

# Configure Loguru with colors
logger.configure(
    handlers=[
        {
            "sink": sys.stderr,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            "colorize": True,
        }
    ]
)

# Export the configured logger
logger = logger
