import json
import pytest
from hackathon_intelligence.observability import (
    RunTrace,
    TokenUsageTrace,
    ToolCallTrace,
    ResearchMetricsTrace,
)
from hackathon_intelligence.schemas import HackathonProfile, JudgingWeight
from hackathon_intelligence.ranking import parse_weights


def test_token_summing_across_llm_calls():
    usage = TokenUsageTrace()
    
    # Event 1: Call 1 (e.g. prompt: 1000, output: 500)
    usage.accumulate(prompt_tok=1000, output_tok=500, total_tok=1500)
    
    # Event 2: Call 2 (e.g. prompt: 1200, output: 800)
    usage.accumulate(prompt_tok=1200, output_tok=800, total_tok=2000)

    # SUM total tokens, not max!
    assert usage.prompt_tokens == 2200
    assert usage.output_tokens == 1300
    assert usage.total_tokens == 3500
    assert usage.llm_calls_count == 2


def test_tool_call_vs_search_call_counting():
    trace = RunTrace(run_id="test_counts_123")

    # Record search tool call
    trace.record_tool_call(
        tool_name="search_web",
        args={"query": "test healthcare ai"},
        results=[{"title": "Result 1", "url": "https://example.com", "snippet": "Snippet"}],
        cache_status="MISS",
        duration_ms=150.0
    )

    # Record github search tool call
    trace.record_tool_call(
        tool_name="search_github",
        args={"query": "test repo"},
        results=[],
        cache_status="HIT",
        duration_ms=40.0
    )

    assert trace.tool_calls_count == 2
    assert trace.search_calls_count == 2
    assert trace.research_metrics.search_web_calls == 1
    assert trace.research_metrics.search_github_calls == 1


def test_sanitized_export_json_redacts_secrets():
    trace = RunTrace(run_id="test_secret_export")
    secret_key = "AIzaSyB1234567890abcdefghijklmnopqrstuv"

    trace.record_tool_call(
        tool_name="search_web",
        args={"query": f"test with secret key {secret_key}", "api_key": secret_key},
        results=[],
        cache_status="MISS",
        duration_ms=10.0,
        error=f"Error containing key {secret_key}"
    )

    exported_json = trace.to_sanitized_export_json()
    assert secret_key not in exported_json
    assert "[REDACTED]" in exported_json or "[REDACTED_API_KEY]" in exported_json

    parsed = json.loads(exported_json)
    assert parsed["run_id"] == "test_secret_export"
    assert len(parsed["tool_calls"]) == 1


def test_ranking_weights_detection_in_trace():
    profile_official = HackathonProfile(
        name="Official Hackathon",
        judging_weights=[
            JudgingWeight(criterion="hackathon_fit", weight="40%"),
            JudgingWeight(criterion="impact", weight="30%"),
            JudgingWeight(criterion="novelty", weight="30%"),
        ]
    )
    weights_official = parse_weights(profile_official)
    
    profile_fallback = HackathonProfile(name="Default Hackathon", judging_weights=[])
    weights_fallback = parse_weights(profile_fallback)

    assert weights_official != weights_fallback
    assert len(profile_official.judging_weights) > 0