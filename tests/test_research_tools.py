from hackathon_intelligence import research_tools


def test_invalid_source_type():
    result = research_tools.search_web("test", source_type="bad")
    assert result["success"] is False


def test_batch_limit():
    result = research_tools.run_research_batch([{"query": str(i)} for i in range(5)])
    assert result["success"] is False


def test_fetch_source_rejects_non_http():
    result = research_tools.fetch_source("file:///tmp/test")
    assert result["success"] is False


def test_source_quality_prefers_primary():
    assert research_tools._source_quality("example.gov", "web") > research_tools._source_quality("example.com", "web")
