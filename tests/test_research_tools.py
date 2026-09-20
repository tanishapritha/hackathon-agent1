from hackathon_intelligence import research_tools


def test_search_web_no_api_key(monkeypatch):
    """search_web gracefully returns failure when TAVILY_API_KEY is missing."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    research_tools.tracker.reset()
    result = research_tools.search_web("test query")
    assert result["success"] is False
    assert "TAVILY_API_KEY" in result.get("error", "")


def test_search_web_respects_call_limit(monkeypatch):
    """search_web should refuse further calls once MAX_SEARCH_CALLS is reached."""
    from hackathon_intelligence.config import MAX_SEARCH_CALLS
    research_tools.tracker.reset()
    research_tools.tracker.search_calls = MAX_SEARCH_CALLS  # simulate exhaustion
    result = research_tools.search_web("overflow query")
    assert result["success"] is False
    assert "limit" in result.get("error", "").lower()


def test_search_web_batch_returns_list(monkeypatch):
    """search_web_batch should always return a list."""
    def fake_search(query, max_results=4):
        return {"success": True, "query": query, "results": []}

    monkeypatch.setattr(research_tools, "search_web", fake_search)
    research_tools.tracker.reset()
    results = research_tools.search_web_batch(["topic A", "topic B"])
    assert isinstance(results, list)
    assert len(results) == 2
