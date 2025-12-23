import logging
from typing import Callable

from google import genai
from google.genai import types

from ..config import EditorConfig
from ..utils.retry import with_retry

logger = logging.getLogger(__name__)

USER_PROMPT_PREFIX = "Here's the transcript:\n\n"


async def edit(
    transcript: str,
    config: EditorConfig,
    system_prompt_override: str | None = None,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """
    Edit and format a transcript using Gemini API.

    Args:
        transcript: The raw transcript text to edit
        config: Editor configuration
        system_prompt_override: Optional override for the system prompt
        on_status: Optional callback to report status updates

    Returns:
        The edited and formatted transcript as Markdown
    """
    if not config.api_key:
        raise ValueError("Editor API key is not configured")

    logger.info("Starting transcript editing...")
    if on_status:
        on_status("Editing transcript...")

    # Initialize client
    client = genai.Client(api_key=config.api_key)

    # Use override or default system prompt
    system_prompt = system_prompt_override or config.system_prompt

    # Configure thinking based on level
    thinking_budget = 1024 if config.thinking_level == "low" else 8192

    # Prepare user content
    user_content = USER_PROMPT_PREFIX + transcript

    # Edit with retry support
    edited_text = await with_retry(
        lambda: _edit_transcript(
            client,
            user_content,
            system_prompt,
            config.model,
            config.temperature,
            thinking_budget,
        ),
        max_attempts=3,
        base_delay_ms=1000,
        context="Editing",
    )

    logger.info(f"Editing completed, output length: {len(edited_text)}")
    return edited_text


async def _edit_transcript(
    client: genai.Client,
    user_content: str,
    system_prompt: str,
    model: str,
    temperature: float,
    thinking_budget: int,
) -> str:
    """Edit transcript using Gemini model."""
    logger.info("Processing transcript editing...")

    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        ),
    )

    # Validate response
    text = response.text
    if not text or text.strip() == "":
        error_msg = "Editing returned empty result."
        if hasattr(response, "prompt_feedback") and response.prompt_feedback:
            if hasattr(response.prompt_feedback, "block_reason"):
                error_msg += f" Block reason: {response.prompt_feedback.block_reason}"
        raise ValueError(error_msg)

    return text
