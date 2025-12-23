import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class AuthorizationMiddleware(BaseMiddleware):
    """
    Middleware to check if the user is authorized to use the bot.
    Only allows messages from chat IDs in the whitelist.
    """

    def __init__(self, allowed_chat_ids: list[int]):
        """
        Initialize the middleware.

        Args:
            allowed_chat_ids: List of authorized chat IDs
        """
        self.allowed_chat_ids = set(allowed_chat_ids)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Process the event and check authorization.
        """
        # Only check Message events
        if not isinstance(event, Message):
            return await handler(event, data)

        message: Message = event
        chat_id = message.chat.id

        # Check if chat ID is authorized
        if chat_id not in self.allowed_chat_ids:
            logger.warning(
                f"Unauthorized access attempt from chat_id: {chat_id}, "
                f"user: {message.from_user.username if message.from_user else 'unknown'}"
            )
            await message.answer(
                "Sorry, you are not authorized to use this bot. "
                "Please contact the administrator."
            )
            return None

        # Authorized - continue to handler
        return await handler(event, data)
