import json
from pathlib import Path
from hackathon_intelligence.logger import log_run, LOG_FILE


def test_log_run_creates_valid_jsonl():
    metrics = log_run(
        run_id="test_run_123",
        status="success",
        duration_ms=123.4,
        requested_ideas=5,
        returned_ideas=5,
        llm_calls=2,
        tool_calls=3,
        cache_hits=1,
        cache_misses=2,
        search_calls=3,
        sources_retrieved=15,
        sources_deduplicated=10,
        sources_selected=8,
        prompt_tokens=500,
        output_tokens=200,
        total_tokens=700,
        retries=0,
        validation_failures=0,
    )

    assert LOG_FILE.exists()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        last_line = lines[-1]
        data = json.loads(last_line)
        assert data["run_id"] == "test_run_123"
        assert data["total_tokens"] == 700