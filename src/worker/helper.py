from email.header import decode_header
import re
from bs4 import BeautifulSoup


def decode_str(header_value: str) -> str:
    """Properly decodes RFC 2047 headers (accents, specific character sets)."""
    if not header_value:
        return ""
    decoded_parts = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            decoded_parts.append(
                part.decode(encoding or "utf-8", errors="ignore")
            )
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def strip_html(html_content: str) -> str:
    """Extracts plain text from HTML by stripping scripts, styles, and tags."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove invisible elements, CSS, JS, and metadata
    for tag in soup(
        ["script", "style", "head", "title", "meta", "noscript", "svg"]
    ):
        tag.decompose()

    # Remove all images (including base64 strings and <img> tags)
    for img in soup.find_all("img"):
        img.decompose()

    return soup.get_text(separator="\n")


def clean_text(text: str) -> str:
    """Cleans text: strips email reply chains, quotes, and excessive line breaks."""
    # Split common reply/forward header patterns
    reply_patterns = [
        r"-+Original Message-+",
        r"-+Forwarded message-+",
        r"On\s+.*,\s+.*wrote:",
        r"Le\s+.*,\s+.*a écrit\s*:",
    ]
    for pattern in reply_patterns:
        text = re.split(pattern, text, flags=re.IGNORECASE)[0]

    # Remove lines starting with '>' (quote lines)
    lines = [
        line.strip()
        for line in text.splitlines()
        if not line.strip().startswith(">")
    ]

    # Reassemble text avoiding multiple consecutive blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return cleaned.strip()
