import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path("C:/Users/tprit/PROJECTS/hackathon-agent/.env")
load_dotenv(ENV_PATH)

from hackathon_intelligence.schemas import HackathonRequest
from runner import run_hackathon_agent_sync

def main():
    print("==================================================")
    print("STARTING HACKATHON INTELLIGENCE BENCHMARK SUITE")
    print("==================================================")

    test_inputs = [
        {
            "name": "Benchmark 1: Healthcare AI Hackathon",
            "request": HackathonRequest(
                hackathon_text="Build innovative AI solutions for healthcare. Focus areas: clinical workflow optimization, medical imaging support, administrative burden reduction, and patient engagement. Track: Healthcare Innovation.",
                user_idea="Radiology report auto-summarizer and anomaly detector",
                additional_context="Must use privacy-compliant workflows and open-source models.",
                num_ideas=5
            )
        },
        {
            "name": "Benchmark 2: DevTools & Infra Hackathon",
            "request": HackathonRequest(
                hackathon_text="Developer tools hackathon focused on AI agent observability, latency optimization, schema validation, and evaluation frameworks for production LLM pipelines.",
                user_idea="Real-time agent debugger and prompt tracing toolkit",
                additional_context="Targeting Python and TypeScript developer workflows.",
                num_ideas=5
            )
        },
        {
            "name": "Benchmark 3: Sustainability & Climate Tech Hackathon",
            "request": HackathonRequest(
                hackathon_text="Hackathon focused on climate change mitigation, scope 3 carbon tracking, renewable energy forecasting, and circular economy market solutions.",
                user_idea="Supply chain carbon footprint estimator",
                additional_context="Focus on verifiable data and open APIs.",
                num_ideas=5
            )
        },
        {
            "name": "Benchmark 4: Repeated Request (Cache Hit Test)",
            "request": HackathonRequest(
                hackathon_text="Build innovative AI solutions for healthcare. Focus areas: clinical workflow optimization, medical imaging support, administrative burden reduction, and patient engagement. Track: Healthcare Innovation.",
                user_idea="Radiology report auto-summarizer and anomaly detector",
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
            ideas_set, metrics = run_hackathon_agent_sync(item["request"])
            dur = time.perf_counter() - start
            results.append({
                "name": item["name"],
                "status": metrics.get("status"),
                "ideas_count": len(ideas_set.ideas),
                "sources_count": len(ideas_set.sources),
                "duration_s": round(dur, 2),
                "duration_ms": metrics.get("duration_ms"),
                "llm_calls": metrics.get("llm_calls"),
                "tool_calls": metrics.get("tool_calls"),
                "cache_hits": metrics.get("cache_hits"),
                "cache_misses": metrics.get("cache_misses"),
                "search_calls": metrics.get("search_calls"),
                "sources_retrieved": metrics.get("sources_retrieved"),
                "sources_deduplicated": metrics.get("sources_deduplicated"),
                "sources_selected": metrics.get("sources_selected"),
                "prompt_tokens": metrics.get("prompt_tokens"),
                "output_tokens": metrics.get("output_tokens"),
                "total_tokens": metrics.get("total_tokens"),
                "retries": metrics.get("retries"),
                "validation_failures": metrics.get("validation_failures"),
            })
            print(f"-> SUCCESS ({len(ideas_set.ideas)} ideas in {dur:.2f}s)")
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

    benchmark_file = Path("C:/Users/tprit/PROJECTS/hackathon-agent/logs/benchmark_results.json")
    benchmark_file.parent.mkdir(parents=True, exist_ok=True)
    with open(benchmark_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()