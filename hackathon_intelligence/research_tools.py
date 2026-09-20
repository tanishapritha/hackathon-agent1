import os
import time
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from tavily import TavilyClient
from .config import (
    MAX_SEARCH_CALLS,
    MAX_RESULTS_PER_SEARCH,
    MAX_SELECTED_SOURCES,
    MAX_SNIPPET_LENGTH,
)
from .research_cache import (
    canonicalize_url,
    get_search_cache,
    normalize_query,
    set_search_cache,
)
from .observability import RunTrace, RunTraceEvent


class ResearchTracker:
    def __init__(self):
        self.search_calls = 0
        self.sources_retrieved = 0
        self.sources_deduplicated = 0
        self.sources_selected = 0
        self.seen_urls = set()
        self.active_trace: Optional[RunTrace] = None
        self.event_callback = None

    def reset(self, trace: Optional[RunTrace] = None, event_callback = None):
        self.search_calls = 0
        self.sources_retrieved = 0
        self.sources_deduplicated = 0
        self.sources_selected = 0
        self.seen_urls.clear()
        self.active_trace = trace
        self.event_callback = event_callback

    def to_dict(self) -> Dict[str, int]:
        return {
            "search_calls": self.search_calls,
            "sources_retrieved": self.sources_retrieved,
            "sources_deduplicated": self.sources_deduplicated,
            "sources_selected": self.sources_selected,
        }


tracker = ResearchTracker()


def compact_snippet(text: str, max_len: int = MAX_SNIPPET_LENGTH) -> str:
    """Trim raw snippet into compact evidence representation."""
    if not text:
        return ""
    clean = " ".join(text.split())
    if len(clean) > max_len:
        return clean[:max_len] + "..."
    return clean


def search_web(query: str, max_results: int = 4) -> Dict[str, Any]:
    """
    Search the web for current information needed for hackathon research.
    Enforces caching, URL deduplication, and compact snippet formatting.
    """
    t0 = time.perf_counter()

    if tracker.search_calls >= MAX_SEARCH_CALLS:
        err_msg = f"Search limit reached ({MAX_SEARCH_CALLS} calls)."
        if tracker.active_trace:
            _, ev = tracker.active_trace.record_tool_call(
                tool_name="search_web",
                args={"query": query, "max_results": max_results},
                results=[],
                cache_status="MISS",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error=err_msg
            )
            if tracker.event_callback:
                tracker.event_callback(ev)
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": err_msg,
        }

    tracker.search_calls += 1
    norm_q = normalize_query(query)
    max_results = max(1, min(max_results, MAX_RESULTS_PER_SEARCH))

    # 1. Check cache
    cached = get_search_cache(norm_q, provider="tavily", max_results=max_results)
    if cached is not None:
        deduped = []
        for item in cached:
            canon_u = canonicalize_url(item.get("url", ""))
            if canon_u and canon_u not in tracker.seen_urls:
                tracker.seen_urls.add(canon_u)
                item["url"] = canon_u
                deduped.append(item)
        
        tracker.sources_retrieved += len(cached)
        tracker.sources_deduplicated += len(deduped)
        tracker.sources_selected += len(deduped)
        dur = (time.perf_counter() - t0) * 1000.0

        if tracker.active_trace:
            _, ev = tracker.active_trace.record_tool_call(
                tool_name="search_web",
                args={"query": query, "max_results": max_results},
                results=deduped,
                cache_status="HIT",
                duration_ms=dur
            )
            if tracker.event_callback:
                tracker.event_callback(ev)

        return {"success": True, "query": query, "results": deduped, "cached": True}

    # 2. Cache miss -> Tavily search
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        err_msg = "TAVILY_API_KEY is not configured."
        dur = (time.perf_counter() - t0) * 1000.0
        if tracker.active_trace:
            _, ev = tracker.active_trace.record_tool_call(
                tool_name="search_web",
                args={"query": query, "max_results": max_results},
                results=[],
                cache_status="MISS",
                duration_ms=dur,
                error=err_msg
            )
            if tracker.event_callback:
                tracker.event_callback(ev)
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": err_msg,
        }

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=norm_q,
            max_results=max_results,
            search_depth="advanced",
            include_answer=False,
            include_raw_content=False,
        )

        raw_items = response.get("results", [])
        tracker.sources_retrieved += len(raw_items)

        cache_store = []
        results = []

        for item in raw_items:
            raw_url = item.get("url", "")
            canon_u = canonicalize_url(raw_url)
            if not canon_u:
                continue

            snippet = compact_snippet(item.get("content", ""))
            source_item = {
                "title": item.get("title", "").strip(),
                "url": canon_u,
                "snippet": snippet,
                "published_date": item.get("published_date"),
                "domain": urlparse(canon_u).netloc,
            }
            cache_store.append(source_item)

            if canon_u not in tracker.seen_urls:
                tracker.seen_urls.add(canon_u)
                results.append(source_item)

        tracker.sources_deduplicated += len(cache_store)
        tracker.sources_selected += len(results)

        # Store in cache
        set_search_cache(norm_q, cache_store, provider="tavily", max_results=max_results)
        dur = (time.perf_counter() - t0) * 1000.0

        if tracker.active_trace:
            _, ev = tracker.active_trace.record_tool_call(
                tool_name="search_web",
                args={"query": query, "max_results": max_results},
                results=results,
                cache_status="MISS",
                duration_ms=dur
            )
            if tracker.event_callback:
                tracker.event_callback(ev)

        return {"success": True, "query": query, "results": results, "cached": False}

    except Exception as exc:
        dur = (time.perf_counter() - t0) * 1000.0
        err_str = str(exc)
        if tracker.active_trace:
            _, ev = tracker.active_trace.record_tool_call(
                tool_name="search_web",
                args={"query": query, "max_results": max_results},
                results=[],
                cache_status="MISS",
                duration_ms=dur,
                error=err_str
            )
            if tracker.event_callback:
                tracker.event_callback(ev)
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": err_str,
        }


def search_web_batch(queries: List[str], max_results: int = 4) -> List[Dict[str, Any]]:
    """Execute multiple independent searches concurrently."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries) or 1) as executor:
        future_to_query = {
            executor.submit(search_web, q, max_results): q for q in queries
        }
        for future in concurrent.futures.as_completed(future_to_query):
            try:
                data = future.result()
                results.append(data)
            except Exception as exc:
                q = future_to_query[future]
                results.append({"success": False, "query": q, "results": [], "error": str(exc)})
    return results