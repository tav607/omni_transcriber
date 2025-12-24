import asyncio
import logging
import os
import re

import markdown
from weasyprint import HTML, CSS, default_url_fetcher

logger = logging.getLogger(__name__)


# Pattern to strip HTML tags that could be injected
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _safe_url_fetcher(url: str, timeout: int = 10, ssl_context=None):
    """
    Custom URL fetcher that blocks all external resources to prevent SSRF.

    Only allows data: URIs for inline content.
    Blocks file://, http://, https://, and any other schemes.
    """
    if url.startswith("data:"):
        # Allow data URIs (inline content)
        return default_url_fetcher(url, timeout, ssl_context)

    # Block all other URLs to prevent SSRF and local file access
    logger.warning(f"Blocked attempt to fetch external resource: {url}")
    # Return empty content instead of raising an error
    return {
        "string": b"",
        "mime_type": "text/plain",
    }


def _sanitize_html(html_content: str) -> str:
    """
    Remove potentially dangerous HTML elements from content.

    This is a defense-in-depth measure - the url_fetcher also blocks resources.
    """
    # Remove script tags and their content
    html_content = re.sub(
        r"<script[^>]*>.*?</script>",
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove style tags with @import or url()
    html_content = re.sub(
        r"<style[^>]*>.*?</style>",
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove iframe, object, embed, frame tags
    html_content = re.sub(
        r"<(iframe|object|embed|frame|link)[^>]*>",
        "",
        html_content,
        flags=re.IGNORECASE,
    )

    # Remove event handlers (onclick, onerror, etc.)
    html_content = re.sub(
        r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']",
        "",
        html_content,
        flags=re.IGNORECASE,
    )

    # Remove src/href attributes pointing to file:// or javascript:
    html_content = re.sub(
        r"\s+(src|href)\s*=\s*[\"'](file:|javascript:)[^\"']*[\"']",
        "",
        html_content,
        flags=re.IGNORECASE,
    )

    return html_content

DEFAULT_CSS = """
@page {
    size: A4;
    margin: 2cm;
}

body {
    font-family: "Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "WenQuanYi Micro Hei", sans-serif;
    font-size: 12pt;
    line-height: 1.6;
    color: #333;
}

h1 {
    font-size: 24pt;
    color: #1a1a1a;
    border-bottom: 2px solid #333;
    padding-bottom: 0.3em;
    margin-top: 1em;
}

h2 {
    font-size: 18pt;
    color: #2a2a2a;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.2em;
    margin-top: 1.5em;
}

h3 {
    font-size: 14pt;
    color: #3a3a3a;
    margin-top: 1em;
}

p {
    margin: 0.8em 0;
    text-align: justify;
}

ul, ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
}

li {
    margin: 0.3em 0;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 1.5em 0;
}

code {
    font-family: "Fira Code", "Source Code Pro", "Consolas", monospace;
    background-color: #f5f5f5;
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-size: 0.9em;
}

pre {
    background-color: #f5f5f5;
    padding: 1em;
    border-radius: 5px;
    overflow-x: auto;
    font-size: 0.9em;
}

blockquote {
    border-left: 4px solid #ddd;
    margin: 1em 0;
    padding-left: 1em;
    color: #666;
}
"""


async def generate_pdf(markdown_content: str, output_path: str) -> str:
    """
    Generate a PDF from Markdown content.

    Args:
        markdown_content: The Markdown content to convert
        output_path: Path to save the PDF file

    Returns:
        Path to the generated PDF file
    """
    logger.info("Generating PDF from Markdown...")

    # Convert Markdown to HTML
    html_content = markdown.markdown(
        markdown_content,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )

    # Sanitize HTML to remove potentially dangerous elements
    html_content = _sanitize_html(html_content)

    # Wrap in HTML document structure
    full_html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript</title>
</head>
<body>
{html_content}
</body>
</html>
"""

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Generate PDF in thread pool (WeasyPrint is synchronous)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: _generate_pdf_sync(full_html, output_path)
    )

    logger.info(f"PDF generated: {output_path}")
    return output_path


def _generate_pdf_sync(html_content: str, output_path: str) -> None:
    """Generate PDF synchronously (for thread pool execution)."""
    # Use custom url_fetcher to block all external resources (SSRF prevention)
    html = HTML(string=html_content, url_fetcher=_safe_url_fetcher)
    css = CSS(string=DEFAULT_CSS)
    html.write_pdf(output_path, stylesheets=[css])
