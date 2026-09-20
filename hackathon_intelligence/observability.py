import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from .logger import redact_secrets


class RunTraceEvent(BaseModel):
    type: str  # "stage", "llm_call", "tool_call", "cache_hit", "ranking", "complete", "error"
    timestamp: str
    stage: Optional[str] = None
    tool_name: Optional[str] = None
    model: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    result_count: int = 0
    cache_status: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    message: Optional[str] = None
    error: Optional[str] = None


class ToolCallTrace(BaseModel):
    seq_num: int
    timestamp: str
    tool_name: str
    sanitized_args: Dict[str, Any]
    result_count: int = 0
    compact_evidence: List[Dict[str, str]] = Field(default_factory=list)
    cache_status: str = "MISS"
    duration_ms: float = 0.0
    error: Optional[str] = None


class StageTrace(BaseModel):
    name: str
    timestamp: str
    duration_ms: float = 0.0
    status: str = "completed"


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
    model: str = "gemini-3.6-flash"
    status: str = "pending"
    duration_ms: float = 0.0
    requested_ideas: int = 5
    returned_ideas: int = 0
    
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
    ) -> Tuple[ToolCallTrace, RunTraceEvent]:
        self.tool_calls_count += 1
        
        if "search" in tool_name.lower():
            self.search_calls_count += 1
            if "github" in tool_name.lower():
                self.research_metrics.search_github_calls += 1
            elif "reddit" in tool_name.lower():
                self.research_metrics.search_reddit_calls += 1
            else:
                self.research_metrics.search_web_calls += 1

        sanitized_args = {}
        for k, v in args.items():
            if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                sanitized_args[k] = "[REDACTED]"
            else:
                sanitized_args[k] = redact_secrets(str(v)[:200])

        compact_ev = []
        for item in results[:5]:
            compact_ev.append({
                "title": str(item.get("title") or item.get("name") or "Result"),
                "domain": str(item.get("domain") or "web"),
                "url": redact_secrets(str(item.get("url") or "")),
                "snippet": redact_secrets(str(item.get("snippet") or item.get("evidence") or "")[:200]),
            })

        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        trace_item = ToolCallTrace(
            seq_num=len(self.tool_calls) + 1,
            timestamp=now_str,
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

        event = RunTraceEvent(
            type="tool_call",
            timestamp=now_str,
            tool_name=tool_name,
            args=sanitized_args,
            result_count=len(results),
            cache_status=cache_status,
            duration_ms=round(duration_ms, 2),
            error=redact_secrets(error)
        )

        return trace_item, event

    def record_stage(self, name: str, duration_ms: float = 0.0, status: str = "completed") -> RunTraceEvent:
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        self.stages.append(StageTrace(
            name=name,
            timestamp=now_str,
            duration_ms=round(duration_ms, 2),
            status=status
        ))
        return RunTraceEvent(
            type="stage",
            timestamp=now_str,
            stage=name,
            duration_ms=round(duration_ms, 2),
            message=f"✓ {name}"
        )

    def record_llm_call(
        self,
        call_num: int,
        prompt_tokens: int,
        output_tokens: int,
        total_tokens: int,
        duration_ms: float,
        purpose: str
    ) -> RunTraceEvent:
        self.token_usage.accumulate(prompt_tokens, output_tokens, total_tokens)
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        return RunTraceEvent(
            type="llm_call",
            timestamp=now_str,
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens if total_tokens > 0 else (prompt_tokens + output_tokens),
            duration_ms=round(duration_ms, 2),
            message=f"🧠 {self.model} · Call {call_num}/4 ({purpose})"
        )

    def to_sanitized_export_json(self) -> str:
        """Return clean JSON string without secrets for UI export."""
        data = self.model_dump(exclude_none=True)
        raw = json.dumps(data, indent=2)
        return redact_secrets(raw) or "{}"