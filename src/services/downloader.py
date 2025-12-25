import asyncio
import logging
import os
import tempfile
from typing import Callable

import yt_dlp

from ..utils.url_parser import (
    extract_video_id,
    extract_bilibili_video_id,
    is_bilibili_url,
    extract_apple_podcasts_id,
    is_apple_podcasts_url,
)

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Exception raised for audio download errors."""

    pass


async def download_audio(
    url: str,
    output_dir: str | None = None,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """
    Download audio from a video URL (YouTube, Bilibili, or Apple Podcasts).

    Args:
        url: Video/podcast URL
        output_dir: Directory to save the audio file (uses temp dir if not specified)
        on_status: Optional callback to report status updates

    Returns:
        Path to the downloaded audio file

    Raises:
        DownloadError: If the video ID cannot be extracted or download fails
    """
    # Try to extract video ID based on URL type
    if is_bilibili_url(url):
        video_id = extract_bilibili_video_id(url)
    elif is_apple_podcasts_url(url):
        video_id = extract_apple_podcasts_id(url)
    else:
        video_id = extract_video_id(url)

    if not video_id:
        raise DownloadError(f"Could not extract video ID from URL: {url}")

    logger.info(f"Downloading audio for video: {video_id}")
    if on_status:
        on_status("Downloading audio from YouTube...")

    # Use temp directory if not specified
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Output template
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")

    # yt-dlp options for audio extraction
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    # Run yt-dlp in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    try:
        output_path = await loop.run_in_executor(
            None, lambda: _download_with_ytdlp(url, ydl_opts, video_id, output_dir)
        )
    except Exception as e:
        raise DownloadError(f"Failed to download audio: {e}") from e

    if not os.path.exists(output_path):
        raise DownloadError(f"Downloaded file not found: {output_path}")

    logger.info(f"Audio downloaded: {output_path}")
    return output_path


def _download_with_ytdlp(
    url: str, ydl_opts: dict, video_id: str, output_dir: str
) -> str:
    """
    Download audio using yt-dlp (synchronous function for thread pool).
    """
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Extract info first to get the actual output filename
        info = ydl.extract_info(url, download=True)

        if info is None:
            raise DownloadError("Failed to extract video info")

        # The output file should be video_id.mp3 after postprocessing
        output_path = os.path.join(output_dir, f"{video_id}.mp3")

        # If not found, try to find any file with the video_id
        if not os.path.exists(output_path):
            for ext in ["mp3", "m4a", "webm", "opus", "wav"]:
                candidate = os.path.join(output_dir, f"{video_id}.{ext}")
                if os.path.exists(candidate):
                    output_path = candidate
                    break

        return output_path


async def get_video_info(url: str) -> dict | None:
    """
    Get video information without downloading.

    Args:
        url: YouTube URL

    Returns:
        Video info dict or None if extraction fails
    """
    video_id = extract_video_id(url)
    if not video_id:
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(
            None, lambda: _get_info_with_ytdlp(url, ydl_opts)
        )
        return info
    except Exception as e:
        logger.warning(f"Failed to get video info: {e}")
        return None


def _get_info_with_ytdlp(url: str, ydl_opts: dict) -> dict | None:
    """Get video info using yt-dlp (synchronous function for thread pool)."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)
