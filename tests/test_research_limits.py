from hackathon_intelligence.research_tools import (
    search_web,
    tracker,
    MAX_SEARCH_CALLS,
    compact_snippet
)


def test_compact_snippet():
    long_text = "word " * 200
    snippet = compact_snippet(long_text, max_len=50)
    assert len(snippet) <= 53
    assert snippet.endswith("...")


def test_search_budget_enforcement():
    tracker.reset()
    tracker.search_calls = MAX_SEARCH_CALLS
    res = search_web("some query")
    assert res["success"] is False
    assert "limit reached" in res["error"].lower()