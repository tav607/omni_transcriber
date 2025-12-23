import re
import logging
import os
from typing import Callable

from google import genai
from google.genai import types

from ..config import TranscriberConfig
from ..utils.retry import with_retry

logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = (
    "Transcribe this audio. If the language is Chinese, please use Simplified "
    "Chinese characters. Provide only the direct transcription text without any "
    "introductory phrases."
)


def cleanup_repetitive_characters(text: str, max_repeats: int = 10) -> str:
    """
    Clean up repetitive characters in transcription result.
    Remove sequences where the same character repeats more than a threshold.
    """
    if not text:
        return text

    pattern = rf"(.)\1{{{max_repeats},}}"

    def replacer(match: re.Match) -> str:
        char = match.group(1)
        logger.info(
            f"Found repetitive character '{char}' repeated {len(match.group(0))} times, "
            "cleaning to single occurrence"
        )
        return char

    return re.sub(pattern, replacer, text)


async def transcribe(
    audio_path: str,
    config: TranscriberConfig,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """
    Transcribe audio file using Gemini API.

    Args:
        audio_path: Path to the audio file to transcribe
        config: Transcriber configuration
        on_status: Optional callback to report status updates

    Returns:
        The transcribed text
    """
    if not config.api_key:
        raise ValueError("Transcriber API key is not configured")

    logger.info("Starting audio transcription processing...")

    # Initialize client
    client = genai.Client(api_key=config.api_key)

    # Get MIME type based on file extension
    ext = os.path.splitext(audio_path)[1].lower()
    mime_types = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    mime_type = mime_types.get(ext, "audio/mpeg")

    # Upload audio file
    logger.info("Uploading audio to Gemini File API...")
    if on_status:
        on_status("Uploading audio...")

    uploaded_file = await with_retry(
        lambda: _upload_file(client, audio_path, mime_type),
        max_attempts=3,
        base_delay_ms=1000,
        context="File upload",
    )
    logger.info(f"Audio uploaded: {uploaded_file.name}")

    # Configure thinking based on level
    thinking_budget = 1024 if config.thinking_level == "low" else 8192

    # Transcribe with retry support
    if on_status:
        on_status("Transcribing...")

    try:
        full_text = await with_retry(
            lambda: _transcribe_audio(
                client,
                uploaded_file,
                config.model,
                config.temperature,
                thinking_budget,
            ),
            max_attempts=3,
            base_delay_ms=1000,
            context="Transcription",
        )
        logger.info(f"Transcription completed, text length: {len(full_text)}")
    finally:
        # Always clean up uploaded file
        logger.info("Cleaning up uploaded file...")
        if on_status:
            on_status("Cleaning up...")
        try:
            await _delete_file(client, uploaded_file.name)
            logger.info("Uploaded file cleaned up")
        except Exception:
            logger.warning(
                "Failed to clean up uploaded file, it may remain on Gemini servers"
            )

    # Clean up repetitive characters
    logger.info("Cleaning up repetitive characters...")
    before_cleanup = len(full_text)
    full_text = cleanup_repetitive_characters(full_text)
    after_cleanup = len(full_text)
    cleanup_reduction = before_cleanup - after_cleanup

    if cleanup_reduction > 0:
        logger.info(
            f"Cleanup completed. Removed {cleanup_reduction} repetitive characters "
            f"({cleanup_reduction / before_cleanup * 100:.1f}%)"
        )
    else:
        logger.info("Cleanup completed. No repetitive characters found.")

    logger.info("Transcription process completed!")
    return full_text


async def _upload_file(
    client: genai.Client, file_path: str, mime_type: str
) -> types.File:
    """Upload a file to Gemini File API."""
    return client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(mime_type=mime_type),
    )


async def _transcribe_audio(
    client: genai.Client,
    uploaded_file: types.File,
    model: str,
    temperature: float,
    thinking_budget: int,
) -> str:
    """Transcribe audio using Gemini model."""
    logger.info("Processing transcription...")

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=TRANSCRIPTION_PROMPT),
                    types.Part.from_uri(
                        file_uri=uploaded_file.uri,
                        mime_type=uploaded_file.mime_type,
                    ),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        ),
    )

    # Validate response
    text = response.text
    if not text or text.strip() == "":
        error_msg = "Transcription returned empty result."
        if hasattr(response, "prompt_feedback") and response.prompt_feedback:
            if hasattr(response.prompt_feedback, "block_reason"):
                error_msg += f" Block reason: {response.prompt_feedback.block_reason}"
        raise ValueError(error_msg)

    return text


async def _delete_file(client: genai.Client, file_name: str) -> None:
    """Delete a file from Gemini File API."""
    client.files.delete(name=file_name)
