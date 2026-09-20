import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .logger import redact_secrets


class ToolCallTrace(BaseModel):
    seq_num: int
    timestamp: str
    tool_name: str
    sanitized_args: Dict[str, Any]
    result_count: int = 0
    compact_evidence: List[Dict[str, str]] = Field(default_factory=list)
    cache_status: str = "MISS"  # "HIT" or "MISS"
    duration_ms: float = 0.0
    error: Optional[str] = None


class StageTrace(BaseModel):
    name: str
    timestamp: str
    duration_ms: float = 0.0
    status: str = "completed"  # "completed" | "failed" | "skipped"


class TokenUsageTrace(BaseModel):
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0
    llm_calls_count: int = 0

    def accumulate(self, prompt_tok: int, output_tok: int, total_tok: int = 0, cached_tok: int = 0):
        """Sum token usage across LLM calls instead of taking max."""
        self.prompt_tokens += max(0, prompt_tok)
        self.output_tokens += max(0, output_tok)
        calculated_total = total_tok if total_tok > 0 else (prompt_tok + output_tok)
        self.total_tokens += max(0, calculated_total)
        self.cached_input_tokens += max(0, cached_tok)
        self.llm_calls_count += 1


class ResearchMetricsTrace(BaseModel):
    searches_performed: int = 0
    results_retrieved: int = 0
    duplicates_removed: int = 0
    sources_selected: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    search_web_calls: int = 0
    search_github_calls: int = 0
    search_reddit_calls: int = 0


class CacheMetricsTrace(BaseModel):
    request_cache_hit: bool = False
    research_cache_hits: int = 0
    research_cache_misses: int = 0
    search_calls_avoided: int = 0
    cached_sources_reused: int = 0
    hit_rate_pct: float = 0.0


class RankingMetricsTrace(BaseModel):
    weights_type: str = "Using fallback ranking weights"
    weights: Dict[str, float] = Field(default_factory=dict)
    ideas_scores: List[Dict[str, Any]] = Field(default_factory=list)


class ErrorMetricsTrace(BaseModel):
    retries: int = 0
    validation_failures: int = 0
    tool_errors: int = 0
    llm_errors: int = 0
    last_error: Optional[str] = None


class RunTrace(BaseModel):
    run_id: str
    model: str = "gemini-2.5-flash"
    status: str = "pending"
    duration_ms: float = 0.0
    requested_ideas: int = 5
    returned_ideas: int = 0
    
    # Core engineering metrics
    tool_calls_count: int = 0
    search_calls_count: int = 0
    
    token_usage: TokenUsageTrace = Field(default_factory=TokenUsageTrace)
    tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    stages: List[StageTrace] = Field(default_factory=list)
    research_metrics: ResearchMetricsTrace = Field(default_factory=ResearchMetricsTrace)
    cache_metrics: CacheMetricsTrace = Field(default_factory=CacheMetricsTrace)
    ranking_metrics: RankingMetricsTrace = Field(default_factory=RankingMetricsTrace)
    errors: ErrorMetricsTrace = Field(default_factory=ErrorMetricsTrace)

    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        results: List[Dict[str, Any]],
        cache_status: str,
        duration_ms: float,
        error: Optional[str] = None
    ) -> ToolCallTrace:
        self.tool_calls_count += 1
        
        # Categorize per-tool search calls
        if "search" in tool_name.lower():
            self.search_calls_count += 1
            if "github" in tool_name.lower():
                self.research_metrics.search_github_calls += 1
            elif "reddit" in tool_name.lower():
                self.research_metrics.search_reddit_calls += 1
            else:
                self.research_metrics.search_web_calls += 1

        # Sanitize arguments (remove secrets)
        sanitized_args = {}
        for k, v in args.items():
            if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                sanitized_args[k] = "[REDACTED]"
            else:
                sanitized_args[k] = str(v)[:200]

        # Compact evidence format
        compact_ev = []
        for item in results[:5]:
            compact_ev.append({
                "title": str(item.get("title") or item.get("name") or "Result"),
                "domain": str(item.get("domain") or "web"),
                "url": redact_secrets(str(item.get("url") or "")),
                "snippet": redact_secrets(str(item.get("snippet") or item.get("evidence") or "")[:200]),
            })

        trace_item = ToolCallTrace(
            seq_num=len(self.tool_calls) + 1,
            timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            tool_name=tool_name,
            sanitized_args=sanitized_args,
            result_count=len(results),
            compact_evidence=compact_ev,
            cache_status=cache_status,
            duration_ms=round(duration_ms, 2),
            error=redact_secrets(error)
        )

        self.tool_calls.append(trace_item)

        if error:
            self.errors.tool_errors += 1

        return trace_item

    def record_stage(self, name: str, duration_ms: float = 0.0, status: str = "completed"):
        self.stages.append(StageTrace(
            name=name,
            timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            duration_ms=round(duration_ms, 2),
            status=status
        ))

    def to_sanitized_export_json(self) -> str:
        """Return clean JSON string without secrets for UI export."""
        data = self.model_dump(exclude_none=True)
        raw = json.dumps(data, indent=2)
        return redact_secrets(raw) or "{}"