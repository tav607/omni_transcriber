import asyncio
import logging
import os

from .config import config, setup_logging
from .bot.bot import run_bot


def main():
    """Main entry point for the application."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Ensure temp directory exists
    os.makedirs(config.temp_dir, exist_ok=True)

    # Log configuration
    logger.info("Starting Omni Transcriber Bot")
    logger.info(f"Temp directory: {config.temp_dir}")
    logger.info(f"Transcriber model: {config.transcriber.model}")
    logger.info(f"Editor model: {config.editor.model}")
    logger.info(
        f"Allowed chat IDs: {config.telegram.allowed_chat_ids or 'ALL (no restriction)'}"
    )

    # Run the bot
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
