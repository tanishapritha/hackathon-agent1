import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

from hackathon_intelligence.schemas import HackathonRequest
from hackathon_intelligence.runner import run_hackathon_agent_sync

def main():
    print("==================================================")
    print("STARTING HACKATHON INTELLIGENCE BENCHMARK SUITE")
    print("==================================================")

    test_inputs = [
        {
            "name": "TEST 1: Healthcare AI Hackathon (Uncached)",
            "request": HackathonRequest(
                hackathon_text="Build innovative AI solutions for healthcare. Focus areas: clinical workflow optimization, medical imaging support, administrative burden reduction, and patient engagement. Track: Healthcare Innovation.",
                user_idea="Radiology report auto-summarizer and anomaly detector",
                additional_context="Must use privacy-compliant workflows and open-source models.",
                num_ideas=5
            )
        },
        {
            "name": "TEST 2: DevTools & Infra Hackathon",
            "request": HackathonRequest(
                hackathon_text="Developer tools hackathon focused on AI agent observability, latency optimization, schema validation, and evaluation frameworks for production LLM pipelines.",
                user_idea="Real-time agent debugger and prompt tracing toolkit",
                additional_context="Targeting Python and TypeScript developer workflows.",
                num_ideas=5
            )
        },
        {
            "name": "TEST 3: Sustainability & Climate Tech Hackathon",
            "request": HackathonRequest(
                hackathon_text="Hackathon focused on climate change mitigation, scope 3 carbon tracking, renewable energy forecasting, and circular economy market solutions.",
                user_idea="Supply chain carbon footprint estimator",
                additional_context="Focus on verifiable data and open APIs.",
                num_ideas=5
            )
        },
        {
            "name": "TEST 4: Repeat TEST 1 Exactly (Request Cache HIT)",
            "request": HackathonRequest(
                hackathon_text="Build innovative AI solutions for healthcare. Focus areas: clinical workflow optimization, medical imaging support, administrative burden reduction, and patient engagement. Track: Healthcare Innovation.",
                user_idea="Radiology report auto-summarizer and anomaly detector",
                additional_context="Must use privacy-compliant workflows and open-source models.",
                num_ideas=5
            )
        },
        {
            "name": "TEST 5: Same Hackathon, Different Idea (Research Cache Reuse)",
            "request": HackathonRequest(
                hackathon_text="Build innovative AI solutions for healthcare. Focus areas: clinical workflow optimization, medical imaging support, administrative burden reduction, and patient engagement. Track: Healthcare Innovation.",
                user_idea="Clinical trial patient matching and eligibility verification",
                additional_context="Must use privacy-compliant workflows and open-source models.",
                num_ideas=5
            )
        }
    ]

    results = []

    for item in test_inputs:
        print(f"\nRunning {item['name']}...")
        start = time.perf_counter()
        try:
            ideas_set, trace = run_hackathon_agent_sync(item["request"])
            dur = time.perf_counter() - start
            results.append({
                "name": item["name"],
                "status": trace.status,
                "ideas_count": len(ideas_set.ideas),
                "sources_count": len(ideas_set.sources),
                "duration_s": round(dur, 2),
                "duration_ms": trace.duration_ms,
                "llm_calls": trace.token_usage.llm_calls_count,
                "tool_calls": trace.tool_calls_count,
                "search_calls": trace.search_calls_count,
                "cache_hits": trace.research_metrics.cache_hits,
                "cache_misses": trace.research_metrics.cache_misses,
                "request_cache_hit": trace.cache_metrics.request_cache_hit,
                "sources_retrieved": trace.research_metrics.results_retrieved,
                "sources_deduplicated": trace.research_metrics.duplicates_removed,
                "sources_selected": trace.research_metrics.sources_selected,
                "prompt_tokens": trace.token_usage.prompt_tokens,
                "output_tokens": trace.token_usage.output_tokens,
                "total_tokens": trace.token_usage.total_tokens,
                "retries": trace.errors.retries,
                "validation_failures": trace.errors.validation_failures,
            })
            print(f"-> SUCCESS ({len(ideas_set.ideas)} ideas, {trace.token_usage.llm_calls_count} Gemini calls in {dur:.2f}s)")
        except Exception as exc:
            print(f"-> FAILED: {exc}")
            results.append({
                "name": item["name"],
                "status": "failed",
                "error": str(exc)
            })

    print("\n==================================================")
    print("BENCHMARK SUMMARY RESULTS")
    print("==================================================")
    print(json.dumps(results, indent=2))

    benchmark_file = PROJECT_ROOT / "logs" / "benchmark_results.json"
    benchmark_file.parent.mkdir(parents=True, exist_ok=True)
    with open(benchmark_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()