import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ..config import config
from .middleware import AuthorizationMiddleware
from .handlers import router

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Create and configure the Telegram bot."""
    if not config.telegram.bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured")

    return Bot(
        token=config.telegram.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


def create_dispatcher() -> Dispatcher:
    """Create and configure the dispatcher with middleware and handlers."""
    dp = Dispatcher()

    # Register authorization middleware
    if config.telegram.allowed_chat_ids:
        dp.message.middleware(
            AuthorizationMiddleware(config.telegram.allowed_chat_ids)
        )
        logger.info(
            f"Authorization middleware enabled for chat IDs: "
            f"{config.telegram.allowed_chat_ids}"
        )
    else:
        logger.warning(
            "No allowed chat IDs configured! Bot is open to everyone. "
            "Set TELEGRAM_ALLOWED_CHAT_IDS to restrict access."
        )

    # Register handlers
    dp.include_router(router)

    return dp


async def run_bot():
    """Run the bot with polling."""
    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Starting bot...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
