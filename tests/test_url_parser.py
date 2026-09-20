import pytest
from hackathon_intelligence.url_parser import (
    validate_url,
    fetch_hackathon_url,
    TextExtractor,
    MAX_PAGE_SIZE
)


def test_validate_url():
    assert validate_url("https://example.com/hackathon") is True
    assert validate_url("http://devpost.com/hackathons") is True
    assert validate_url("not-a-url") is False
    assert validate_url("ftp://example.com") is False
    assert validate_url("") is False


def test_html_text_extractor():
    html = """
    <html>
        <head><title>Test Hackathon</title><script>var secret=1;</script></head>
        <body>
            <header>Header Navigation</header>
            <nav><a href="#">Nav item</a></nav>
            <h1>AI Healthcare Hackathon 2026</h1>
            <p>Build innovative medical tools. Prize pool $50,000.</p>
            <footer>Footer Links</footer>
        </body>
    </html>
    """
    parser = TextExtractor()
    parser.feed(html)
    text = parser.get_text()

    assert "AI Healthcare Hackathon 2026" in text
    assert "Prize pool $50,000." in text
    assert "var secret=1" not in text
    assert "Header Navigation" not in text
    assert "Footer Links" not in text


def test_fetch_invalid_url():
    res = fetch_hackathon_url("not_a_valid_url")
    assert res["success"] is False
    assert "Invalid URL" in res["error"]


def test_fetch_nonexistent_url():
    res = fetch_hackathon_url("https://this-domain-definitely-does-not-exist-999.org/hackathon")
    assert res["success"] is False
    assert "Couldn't extract the hackathon details from this URL" in res["error"]


def test_url_input_priority_logic():
    # Priority logic: URL > PDF > Text
    url_text = "HACKATHON WEBPAGE SOURCE URL: https://example.com\n\nMain URL content"
    pdf_text = "PDF specification content"
    pasted_text = "Pasted description content"

    # URL + PDF + Text -> Primary is URL with PDF/text as additional context
    combined = url_text + "\n\nATTACHED PDF BRIEF:\n" + pdf_text + "\n\nPASTED TEXT BRIEF:\n" + pasted_text
    assert combined.startswith("HACKATHON WEBPAGE SOURCE URL")
    assert "PDF specification content" in combined
    assert "Pasted description content" in combined