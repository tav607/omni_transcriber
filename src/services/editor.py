import asyncio
import logging
from typing import Callable

from google import genai
from google.genai import types

from ..config import EditorConfig
from ..utils.retry import with_retry

logger = logging.getLogger(__name__)

USER_PROMPT_PREFIX = "Here's the transcript:\n\n"

TRANSLATION_PROMPT_ADDITION = """

## Translation Mode (ENABLED)
Since translation mode is enabled, you must add inline Chinese translations to the Transcript section:

1. **Detect language**: First determine if the transcript is primarily in Chinese
2. **If NOT Chinese**: After each paragraph in the Transcript section, add a blockquote with the Chinese translation
3. **If Chinese**: No translation needed, output normally

### Translation Format
For non-Chinese transcripts, format each paragraph like this:
```
Original paragraph text here.
> 这里是中文翻译。

Next paragraph in original language.
> 下一段的中文翻译。
```

### Translation Requirements
- Translate the meaning accurately, not word-for-word
- Maintain the same paragraph structure
- Use `> ` (blockquote) for all translations
- Keep translations natural and readable in Chinese
"""


async def edit(
    transcript: str,
    config: EditorConfig,
    system_prompt_override: str | None = None,
    enable_translation: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """
    Edit and format a transcript using Gemini API.

    Args:
        transcript: The raw transcript text to edit
        config: Editor configuration
        system_prompt_override: Optional override for the system prompt
        enable_translation: If True, add inline Chinese translations for non-Chinese transcripts
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
    client = genai.Client(
        api_key=config.api_key,
        http_options={"base_url": "https://generativelanguage.googleapis.com"},
    )

    # Use override or default system prompt
    system_prompt = system_prompt_override or config.system_prompt

    # Add translation instructions if enabled
    if enable_translation:
        system_prompt = system_prompt + TRANSLATION_PROMPT_ADDITION
        logger.info("Translation mode enabled")

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

    def _generate():
        return client.models.generate_content(
            model=model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
            ),
        )

    response = await asyncio.to_thread(_generate)

    # Validate response
    text = response.text
    if not text or text.strip() == "":
        error_msg = "Editing returned empty result."
        if hasattr(response, "prompt_feedback") and response.prompt_feedback:
            if hasattr(response.prompt_feedback, "block_reason"):
                error_msg += f" Block reason: {response.prompt_feedback.block_reason}"
        raise ValueError(error_msg)

    return text
