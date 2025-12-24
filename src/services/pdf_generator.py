import asyncio
import logging
import os

import markdown
from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)

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
    html = HTML(string=html_content)
    css = CSS(string=DEFAULT_CSS)
    html.write_pdf(output_path, stylesheets=[css])
