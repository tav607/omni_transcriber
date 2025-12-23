import asyncio
import logging
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay_ms: int = 1000,
    context: str = "Operation",
) -> T:
    """
    Retry an async function with exponential backoff.

    Args:
        fn: The async function to retry
        max_attempts: Maximum number of attempts (default: 3)
        base_delay_ms: Base delay in milliseconds (default: 1000)
        context: Context string for log messages (default: 'Operation')

    Returns:
        The result of the function

    Raises:
        Exception: The last error if all attempts fail
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as error:
            last_error = error
            if attempt < max_attempts:
                delay = base_delay_ms * (2 ** (attempt - 1))
                logger.warning(
                    f"{context} failed (attempt {attempt}/{max_attempts}): {error}. "
                    f"Retrying in {delay}ms..."
                )
                await asyncio.sleep(delay / 1000)

    raise Exception(
        f"{context} failed after {max_attempts} attempts: {last_error}"
    ) from last_error
