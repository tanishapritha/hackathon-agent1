import re
from html.parser import HTMLParser
from urllib.parse import urlparse
import httpx

MAX_PAGE_SIZE = 2 * 1024 * 1024  # 2MB max
FETCH_TIMEOUT = 10.0  # 10 seconds timeout


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = []
        self.ignore_tags = {
            "script", "style", "nav", "footer", "header", 
            "svg", "noscript", "iframe", "form", "button"
        }
        self.current_ignore = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.ignore_tags:
            self.current_ignore.append(t)

    def handle_endtag(self, tag):
        t = tag.lower()
        if self.current_ignore and self.current_ignore[-1] == t:
            self.current_ignore.pop()

    def handle_data(self, data):
        if not self.current_ignore:
            text = data.strip()
            if text:
                self.output.append(text)

    def get_text(self) -> str:
        raw = "\n".join(self.output)
        clean_lines = []
        for line in raw.splitlines():
            line_str = " ".join(line.split())
            if line_str:
                clean_lines.append(line_str)
        return "\n".join(clean_lines)


def validate_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def fetch_hackathon_url(url: str) -> dict:
    """
    Safely fetches and extracts clean hackathon specification text from a URL.
    Returns dict with keys: success, url, text, title, error.
    """
    if not validate_url(url):
        return {
            "success": False,
            "url": url,
            "text": "",
            "error": "Invalid URL provided. Please enter a valid http:// or https:// link."
        }

    clean_u = url.strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
            with client.stream("GET", clean_u) as response:
                if response.status_code >= 400:
                    return {
                        "success": False,
                        "url": clean_u,
                        "text": "",
                        "error": "Couldn't extract the hackathon details from this URL. Try uploading the PDF or pasting the hackathon description instead."
                    }

                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type and "application/xhtml" not in content_type:
                    return {
                        "success": False,
                        "url": clean_u,
                        "text": "",
                        "error": "Couldn't extract the hackathon details from this URL. Try uploading the PDF or pasting the hackathon description instead."
                    }

                content_bytes = bytearray()
                for chunk in response.iter_bytes():
                    content_bytes.extend(chunk)
                    if len(content_bytes) > MAX_PAGE_SIZE:
                        break

                html_content = content_bytes[:MAX_PAGE_SIZE].decode("utf-8", errors="ignore")

        parser = TextExtractor()
        parser.feed(html_content)
        text = parser.get_text()

        if not text or len(text.strip()) < 50:
            return {
                "success": False,
                "url": clean_u,
                "text": "",
                "error": "Couldn't extract the hackathon details from this URL. Try uploading the PDF or pasting the hackathon description instead."
            }

        if len(text) > 15000:
            text = text[:15000] + "\n\n[Content truncated for length]"

        header_prefix = f"HACKATHON WEBPAGE SOURCE URL: {clean_u}\n\n"
        final_text = header_prefix + text

        return {
            "success": True,
            "url": clean_u,
            "text": final_text,
            "raw_text": text,
            "error": None
        }

    except Exception:
        return {
            "success": False,
            "url": clean_u,
            "text": "",
            "error": "Couldn't extract the hackathon details from this URL. Try uploading the PDF or pasting the hackathon description instead."
        }