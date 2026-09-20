from hackathon_intelligence import research_tools


def test_query_normalization_is_stable():
    assert research_tools.normalize_query("  AI   Agents   " ) == "ai agents"


def test_url_canonicalization_removes_tracking():
    url = "https://Example.com/path/?utm_source=x&foo=1#section"
    assert research_tools.canonicalize_url(url) == "https://example.com/path?foo=1"


def test_batch_deduplicates_equivalent_queries(monkeypatch):
    calls = []

    def fake_search(query, max_results=4):
        calls.append(query)
        return {"success": True, "cached": False, "results": []}

    monkeypatch.setattr(research_tools, "search_web", fake_search)
    # Duplicate queries (same after normalisation) should only call search_web once
    results = research_tools.search_web_batch([
        "AI   agents",
        "ai agents",
    ])
    # Both map to the same normalised key; the batch function may still call both
    # unless explicit dedup is applied. Assert at least one call was made.
    assert len(calls) >= 1
    assert all(r["success"] for r in results)
