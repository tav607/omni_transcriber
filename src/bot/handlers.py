import logging
import os
import tempfile
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
        file_name = file.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    elif message.voice:
        file = message.voice
        file_name = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg"
    elif message.document:
        file = message.document
        # Check if it's an audio file
        if file.mime_type and not any(
            mime in file.mime_type for mime in ["audio/", "video/"]
        ):
            # Not an audio file, ignore
            return
        file_name = file.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
    temp_dir = config.temp_dir
    os.makedirs(temp_dir, exist_ok=True)

    audio_path = None
    md_path = None
    pdf_path = None

    try:
        # Download audio
        await status_message.edit_text("Downloading audio from YouTube...")
        audio_path = await download_audio(url, temp_dir)

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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_id = extract_video_id(url) or "video"

        # Save Markdown
        md_path = os.path.join(temp_dir, f"{video_id}_{timestamp}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(edited_transcript)

        # Generate PDF
        pdf_path = os.path.join(temp_dir, f"{video_id}_{timestamp}.pdf")
        await generate_pdf(edited_transcript, pdf_path)

        # Send files
        await status_message.edit_text("Sending files...")

        md_file = FSInputFile(md_path, filename=f"{video_id}_transcript.md")
        pdf_file = FSInputFile(pdf_path, filename=f"{video_id}_transcript.pdf")

        await message.answer_document(md_file, caption="Markdown transcript")
        await message.answer_document(pdf_file, caption="PDF transcript")

        await status_message.edit_text("Done! Your transcript is ready.")

    finally:
        # Cleanup temp files
        for path in [audio_path, md_path, pdf_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


async def _process_audio_file(
    message: Message, file, file_name: str, status_message: Message
) -> None:
    """Process an uploaded audio file and send the transcript."""
    temp_dir = config.temp_dir
    os.makedirs(temp_dir, exist_ok=True)

    audio_path = None
    md_path = None
    pdf_path = None

    try:
        # Download file from Telegram
        await status_message.edit_text("Downloading audio file...")

        # Get file extension
        ext = os.path.splitext(file_name)[1] or ".mp3"
        audio_path = os.path.join(
            temp_dir, f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        )

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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(file_name)[0]

        # Save Markdown
        md_path = os.path.join(temp_dir, f"{base_name}_{timestamp}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(edited_transcript)

        # Generate PDF
        pdf_path = os.path.join(temp_dir, f"{base_name}_{timestamp}.pdf")
        await generate_pdf(edited_transcript, pdf_path)

        # Send files
        await status_message.edit_text("Sending files...")

        md_file = FSInputFile(md_path, filename=f"{base_name}_transcript.md")
        pdf_file = FSInputFile(pdf_path, filename=f"{base_name}_transcript.pdf")

        await message.answer_document(md_file, caption="Markdown transcript")
        await message.answer_document(pdf_file, caption="PDF transcript")

        await status_message.edit_text("Done! Your transcript is ready.")

    finally:
        # Cleanup temp files
        for path in [audio_path, md_path, pdf_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
