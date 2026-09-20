from hackathon_intelligence.research_cache import canonicalize_url


def test_canonicalize_url_strips_tracking_params():
    url = "https://example.com/page?utm_source=google&utm_medium=cpc&fbclid=12345&id=42"
    canon = canonicalize_url(url)
    assert "utm_source" not in canon
    assert "fbclid" not in canon
    assert "id=42" in canon


def test_canonicalize_url_normalizes_casing_and_slashes():
    url = "HTTPS://EXAMPLE.COM/Path/With/Slash/"
    canon = canonicalize_url(url)
    assert canon == "https://example.com/Path/With/Slash"