import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOG_DIR = Path("C:/Users/tprit/PROJECTS/hackathon-agent/logs")
LOG_FILE = LOG_DIR / "run_logs.jsonl"


def redact_secrets(text: Optional[str]) -> Optional[str]:
    """Redact any API key patterns from log strings."""
    if not text:
        return text
    # Redact Google/Gemini API key patterns
    redacted = re.sub(r'AIza[A-Za-z0-9_-]{30,}', '[REDACTED_API_KEY]', text)
    redacted = re.sub(r'AQ\.[A-Za-z0-9_-]{30,}', '[REDACTED_API_KEY]', redacted)
    redacted = re.sub(r'(?:api[_-]?key|secret)["\s:]+["\']?([A-Za-z0-9_-]{20,})["\']?', '[REDACTED_API_KEY]', redacted, flags=re.IGNORECASE)
    return redacted


def log_run(
    run_id: str,
    status: str,
    duration_ms: float,
    requested_ideas: int,
    returned_ideas: int,
    llm_calls: int,
    tool_calls: int,
    cache_hits: int,
    cache_misses: int,
    search_calls: int,
    sources_retrieved: int,
    sources_deduplicated: int,
    sources_selected: int,
    prompt_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    retries: int = 0,
    validation_failures: int = 0,
    model: str = "gemini-2.5-flash",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Write structured JSON log entry for a completed run. Ensures zero secret leakage."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "requested_ideas": requested_ideas,
        "returned_ideas": returned_ideas,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "search_calls": search_calls,
        "sources_retrieved": sources_retrieved,
        "sources_deduplicated": sources_deduplicated,
        "sources_selected": sources_selected,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "retries": retries,
        "validation_failures": validation_failures,
        "error": redact_secrets(error),
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        print(f"Failed to write log entry: {exc}")

    return record