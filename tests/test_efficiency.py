from hackathon_intelligence import research_tools


def test_query_normalization_is_stable():
    assert research_tools._normalize_query("  AI   Agents   " ) == "ai agents"


def test_url_canonicalization_removes_tracking():
    url = "https://Example.com/path/?utm_source=x&foo=1#section"
    assert research_tools._canonical_url(url) == "https://example.com/path?foo=1"


def test_batch_deduplicates_equivalent_queries(monkeypatch):
    calls = []

    def fake_search(query, max_results=5, source_type="web"):
        calls.append((query, source_type))
        return {"success": True, "cached": False, "results": []}

    monkeypatch.setattr(research_tools, "search_web", fake_search)
    result = research_tools.run_research_batch([
        {"query": "AI   agents", "source_type": "web"},
        {"query": "ai agents", "source_type": "web"},
    ])
    assert len(calls) == 1
    assert result["success"] is True
