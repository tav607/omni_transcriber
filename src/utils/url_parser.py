import re
from urllib.parse import urlparse, parse_qs


def extract_video_id(url: str) -> str | None:
    """
    Extract YouTube video ID from various URL formats.

    Supported formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    - https://youtube.com/shorts/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://youtube.com/v/VIDEO_ID

    Args:
        url: The YouTube URL to parse

    Returns:
        The video ID or None if not found
    """
    if not url:
        return None

    url = url.strip()

    # Try parsing as URL first
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Check if it's a YouTube domain
        if not any(
            domain in hostname for domain in ["youtube.com", "youtu.be", "youtube-nocookie.com"]
        ):
            return None

        # Handle youtu.be short URLs
        if "youtu.be" in hostname:
            # Format: https://youtu.be/VIDEO_ID
            video_id = parsed.path.lstrip("/").split("/")[0]
            if video_id and _is_valid_video_id(video_id):
                return video_id

        # Handle youtube.com URLs
        if "youtube" in hostname:
            path = parsed.path

            # Handle /watch URLs
            if path == "/watch" or path.startswith("/watch"):
                query_params = parse_qs(parsed.query)
                video_ids = query_params.get("v", [])
                if video_ids and _is_valid_video_id(video_ids[0]):
                    return video_ids[0]

            # Handle /shorts/ URLs
            if "/shorts/" in path:
                match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", path)
                if match:
                    return match.group(1)

            # Handle /embed/ URLs
            if "/embed/" in path:
                match = re.search(r"/embed/([a-zA-Z0-9_-]{11})", path)
                if match:
                    return match.group(1)

            # Handle /v/ URLs
            if "/v/" in path:
                match = re.search(r"/v/([a-zA-Z0-9_-]{11})", path)
                if match:
                    return match.group(1)

    except Exception:
        pass

    # Fallback: try regex pattern matching on the raw URL
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            if _is_valid_video_id(video_id):
                return video_id

    return None


def _is_valid_video_id(video_id: str) -> bool:
    """
    Check if a string is a valid YouTube video ID.

    YouTube video IDs are 11 characters long and contain only
    alphanumeric characters, hyphens, and underscores.
    """
    if not video_id or len(video_id) != 11:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]{11}$", video_id))


def is_youtube_url(text: str) -> bool:
    """
    Check if a text contains a YouTube URL.

    Args:
        text: The text to check

    Returns:
        True if the text contains a YouTube URL
    """
    return extract_video_id(text) is not None
