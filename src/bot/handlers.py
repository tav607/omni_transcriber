import logging
import os
import re
import shutil
import uuid
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

from ..config import config
from ..utils.url_parser import is_youtube_url, extract_video_id
from ..services.youtube import download_audio
from ..services.transcriber import transcribe
from ..services.editor import edit
from ..services.pdf_generator import generate_pdf

logger = logging.getLogger(__name__)
router = Router()

# Supported audio MIME types
AUDIO_MIME_TYPES = [
    "audio/mpeg",  # mp3
    "audio/mp4",  # m4a
    "audio/x-m4a",  # m4a alternative
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
    "audio/aac",
]

# Allowed characters for sanitized filenames (alphanumeric, hyphen, underscore, dot, CJK)
SAFE_FILENAME_PATTERN = re.compile(r"[^\w\u4e00-\u9fff\-.]", re.UNICODE)

# Pattern to extract h1 title from markdown
H1_TITLE_PATTERN = re.compile(r"^#\s+(.+?)$", re.MULTILINE)


def extract_title_from_transcript(transcript: str) -> str | None:
    """
    Extract the h1 title from a markdown transcript.

    Returns the title text or None if not found.
    """
    match = H1_TITLE_PATTERN.search(transcript)
    if match:
        return match.group(1).strip()
    return None


def sanitize_filename(filename: str, max_length: int = 50) -> str:
    """
    Sanitize a filename to prevent path traversal and other attacks.

    - Extracts basename to remove any path components
    - Replaces unsafe characters with underscores
    - Limits length to prevent filesystem issues
    """
    # Extract just the filename, removing any path components
    filename = os.path.basename(filename)

    # Split into name and extension
    name, ext = os.path.splitext(filename)

    # Replace unsafe characters
    name = SAFE_FILENAME_PATTERN.sub("_", name)
    ext = SAFE_FILENAME_PATTERN.sub("_", ext)

    # Limit length
    if len(name) > max_length:
        name = name[:max_length]

    # Ensure we have a valid name
    if not name:
        name = "file"

    return name + ext


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    await message.answer(
        "Welcome to the AI Transcriber Bot!\n\n"
        "I can help you transcribe audio from:\n"
        "- YouTube videos (send me a YouTube URL)\n"
        "- Audio files (send me an audio file)\n\n"
        "I'll generate a formatted transcript with summary and key points, "
        "delivered as both Markdown and PDF files."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    await message.answer(
        "*How to use this bot:*\n\n"
        "*YouTube Videos:*\n"
        "Simply send me a YouTube URL (long or short format)\n"
        "Example: `https://www.youtube.com/watch?v=...`\n"
        "Example: `https://youtu.be/...`\n\n"
        "*Audio Files:*\n"
        "Send me an audio file (mp3, m4a, wav, webm, etc.)\n\n"
        "*Output:*\n"
        "You'll receive:\n"
        "- A Markdown file with the formatted transcript\n"
        "- A PDF file for easy reading and sharing",
        parse_mode="Markdown",
    )


@router.message(F.audio | F.voice | F.document)
async def handle_audio(message: Message):
    """Handle audio file uploads."""
    # Get the file object
    if message.audio:
        file = message.audio
        file_name = file.file_name or f"audio_{uuid.uuid4().hex[:8]}.mp3"
    elif message.voice:
        file = message.voice
        file_name = f"voice_{uuid.uuid4().hex[:8]}.ogg"
    elif message.document:
        file = message.document
        # Check MIME type - only accept audio files
        if file.mime_type:
            if file.mime_type.startswith("video/"):
                # Reject video files - they need ffmpeg extraction which we don't support
                await message.answer(
                    "Video files are not supported. "
                    "Please extract the audio first or send an audio file directly."
                )
                return
            if not file.mime_type.startswith("audio/"):
                # Not an audio file, ignore
                return
        file_name = file.file_name or f"audio_{uuid.uuid4().hex[:8]}"
    else:
        return

    logger.info(f"Received audio file: {file_name}")
    status_message = await message.answer("Received audio file. Processing...")

    try:
        await _process_audio_file(message, file, file_name, status_message)
    except Exception as e:
        logger.error(f"Error processing audio file: {e}", exc_info=True)
        await status_message.edit_text(f"Error processing audio file: {str(e)}")


@router.message(F.text)
async def handle_text(message: Message):
    """Handle text messages (check for YouTube URLs)."""
    text = message.text
    if not text:
        return

    # Check if it's a YouTube URL
    if is_youtube_url(text):
        video_id = extract_video_id(text)
        logger.info(f"Received YouTube URL, video_id: {video_id}")
        status_message = await message.answer(
            f"Detected YouTube video. Processing...\nVideo ID: `{video_id}`",
            parse_mode="Markdown",
        )

        try:
            await _process_youtube_url(message, text, status_message)
        except Exception as e:
            logger.error(f"Error processing YouTube URL: {e}", exc_info=True)
            await status_message.edit_text(f"Error processing YouTube video: {str(e)}")
    else:
        # Not a YouTube URL, ignore or send help
        await message.answer(
            "Please send me a YouTube URL or an audio file.\n"
            "Use /help for more information."
        )


async def _process_youtube_url(
    message: Message, url: str, status_message: Message
) -> None:
    """Process a YouTube URL and send the transcript."""
    # Create a unique temporary directory for this request to prevent collisions
    request_id = uuid.uuid4().hex[:12]
    request_temp_dir = os.path.join(config.temp_dir, f"yt_{request_id}")
    os.makedirs(request_temp_dir, exist_ok=True)

    try:
        # Download audio
        await status_message.edit_text("Downloading audio from YouTube...")
        audio_path = await download_audio(url, request_temp_dir)

        # Transcribe
        await status_message.edit_text("Transcribing audio...")
        raw_transcript = await transcribe(
            audio_path,
            config.transcriber,
            on_status=lambda s: logger.info(s),
        )

        # Edit/format
        await status_message.edit_text("Formatting transcript...")
        edited_transcript = await edit(
            raw_transcript,
            config.editor,
            on_status=lambda s: logger.info(s),
        )

        # Generate output files
        await status_message.edit_text("Generating output files...")

        # Extract title from transcript for filename
        title = extract_title_from_transcript(edited_transcript)
        if title:
            # Sanitize the title for use as filename
            safe_title = sanitize_filename(title, max_length=30)
        else:
            # Fallback to video_id if no title found
            safe_title = extract_video_id(url) or "transcript"

        # Add date stamp
        date_stamp = datetime.now().strftime("%Y%m%d")
        output_filename = f"{safe_title}_{date_stamp}"

        # Save Markdown
        md_path = os.path.join(request_temp_dir, "transcript.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(edited_transcript)

        # Generate PDF
        pdf_path = os.path.join(request_temp_dir, "transcript.pdf")
        await generate_pdf(edited_transcript, pdf_path)

        # Send files
        await status_message.edit_text("Sending files...")

        md_file = FSInputFile(md_path, filename=f"{output_filename}.md")
        pdf_file = FSInputFile(pdf_path, filename=f"{output_filename}.pdf")

        await message.answer_document(md_file, caption="Markdown transcript")
        await message.answer_document(pdf_file, caption="PDF transcript")

        await status_message.edit_text("Done! Your transcript is ready.")

    finally:
        # Cleanup entire temp directory for this request
        try:
            shutil.rmtree(request_temp_dir)
        except Exception:
            pass


async def _process_audio_file(
    message: Message, file, file_name: str, status_message: Message
) -> None:
    """Process an uploaded audio file and send the transcript."""
    # Sanitize filename to prevent path traversal attacks
    safe_filename = sanitize_filename(file_name)
    base_name = os.path.splitext(safe_filename)[0] or "audio"

    # Create a unique temporary directory for this request to prevent collisions
    request_id = uuid.uuid4().hex[:12]
    request_temp_dir = os.path.join(config.temp_dir, f"audio_{request_id}")
    os.makedirs(request_temp_dir, exist_ok=True)

    try:
        # Download file from Telegram
        await status_message.edit_text("Downloading audio file...")

        # Get file extension (sanitized)
        ext = os.path.splitext(safe_filename)[1] or ".mp3"
        audio_path = os.path.join(request_temp_dir, f"input{ext}")

        # Download file
        await message.bot.download(file, destination=audio_path)

        # Transcribe
        await status_message.edit_text("Transcribing audio...")
        raw_transcript = await transcribe(
            audio_path,
            config.transcriber,
            on_status=lambda s: logger.info(s),
        )

        # Edit/format
        await status_message.edit_text("Formatting transcript...")
        edited_transcript = await edit(
            raw_transcript,
            config.editor,
            on_status=lambda s: logger.info(s),
        )

        # Generate output files
        await status_message.edit_text("Generating output files...")

        # Extract title from transcript for filename
        title = extract_title_from_transcript(edited_transcript)
        if title:
            # Sanitize the title for use as filename
            safe_title = sanitize_filename(title, max_length=30)
        else:
            # Fallback to original filename if no title found
            safe_title = base_name

        # Add date stamp
        date_stamp = datetime.now().strftime("%Y%m%d")
        output_filename = f"{safe_title}_{date_stamp}"

        # Save Markdown
        md_path = os.path.join(request_temp_dir, "transcript.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(edited_transcript)

        # Generate PDF
        pdf_path = os.path.join(request_temp_dir, "transcript.pdf")
        await generate_pdf(edited_transcript, pdf_path)

        # Send files
        await status_message.edit_text("Sending files...")

        md_file = FSInputFile(md_path, filename=f"{output_filename}.md")
        pdf_file = FSInputFile(pdf_path, filename=f"{output_filename}.pdf")

        await message.answer_document(md_file, caption="Markdown transcript")
        await message.answer_document(pdf_file, caption="PDF transcript")

        await status_message.edit_text("Done! Your transcript is ready.")

    finally:
        # Cleanup entire temp directory for this request
        try:
            shutil.rmtree(request_temp_dir)
        except Exception:
            pass
