import re
from urllib.parse import urlparse, parse_qs

# Valid YouTube domains
YOUTUBE_DOMAINS = frozenset(["youtube.com", "youtu.be", "youtube-nocookie.com"])


def _is_youtube_host(hostname: str) -> bool:
    """
    Check if a hostname is a valid YouTube domain.

    Uses strict matching to prevent bypass attacks like youtube.com.evil.com
    """
    if not hostname:
        return False

    hostname = hostname.lower()

    # Check exact match or valid subdomain
    for domain in YOUTUBE_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return True

    return False


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
        hostname = (parsed.hostname or "").lower()

        # Check if it's a valid YouTube domain (strict matching)
        if not _is_youtube_host(hostname):
            return None

        # Handle youtu.be short URLs
        if hostname == "youtu.be" or hostname.endswith(".youtu.be"):
            # Format: https://youtu.be/VIDEO_ID
            video_id = parsed.path.lstrip("/").split("/")[0]
            if video_id and _is_valid_video_id(video_id):
                return video_id

        # Handle youtube.com URLs (hostname already validated by _is_youtube_host)
        if hostname.endswith("youtube.com") or hostname.endswith("youtube-nocookie.com"):
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
        # URL parsing failed - don't use fallback regex as it could match non-YouTube URLs
        pass

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
