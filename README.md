# Hackathon Intelligence Agent

A production-shaped, research-first Google ADK agent for discovering, researching, and deterministically evaluating hackathon project opportunities.

## Key Features & Architecture

- **Single Primary ADK Agent (`root_agent`)**: Uses `gemini-2.5-flash` for high-level semantic understanding, research planning, candidate generation, and critique.
- **SQLite Dual-Layer Caching (`research_cache.py`)**:
  - **Tool-Level Cache**: Caches web search results by normalized query, provider, search bounds, and version TTL.
  - **Request-Level Cache**: Caches identical end-to-end `HackathonRequest` runs, serving valid results in ~5ms without LLM or search calls.
- **Deterministic Python Execution**:
  - URL canonicalization and tracking parameter stripping (`utm_*`, `fbclid`, etc.).
  - Hard-bounded research limits (`MAX_SEARCH_CALLS = 8`, `MAX_RESULTS_PER_SEARCH = 5`, `MAX_SELECTED_SOURCES = 20`, compact 350-char snippets).
  - Score clamping and weighted criteria evaluation (`ranking.py`).
  - Exact requested output count (`N`) enforcement in Python.
- **Structured Pydantic Schemas (`schemas.py`)**: Strong typing for `HackathonProfile`, `OpportunityMap`, `CandidateIdea`, `ResearchSource`, and `FinalIdeaSet`.
- **Structured JSON Telemetry & Observability (`logger.py`)**: Logs one detailed JSON record per run to `logs/run_logs.jsonl` tracking latency, LLM calls, tool calls, token usage, search calls, cache hits/misses, deduplication ratios, retries, and errors.
- **Streamlit Developer Console (`streamlit_app.py`)**: Interactive UI exposing execution metrics, ranked ideas, profile data, and raw event traces.

## System Flow

```
Streamlit / API / Script
        ↓
    runner.py (Request-Level Cache Check)
        ↓
    ADK Root Agent (gemini-2.5-flash)
        ↓
    Bounded Research Tool (search_web)
        ↓
    SQLite Cache + URL Canonicalization & Dedupe
        ↓
    Compact Evidence Summaries
        ↓
    Candidate Idea Generation & Critique
        ↓
    Python Deterministic Ranking & Exact N Count Selection
        ↓
    Pydantic Validation & Telemetry Logging
```

## Setup & Execution

### 1. Environment Variables
Copy `.env.example` to `.env` and configure:
```env
GEMINI_API_KEY=your_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key
```

### 2. Run Streamlit Console
```bash
run.bat
# or manually:
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

### 3. Run Test Suite
```bash
test.bat
# or manually:
.\.venv\Scripts\python.exe -m pytest tests/ --ignore=hackathon_intelligence_final
```

### 4. Run Benchmark Suite
```bash
.\.venv\Scripts\python.exe benchmark.py
```

## Empirical Benchmark Performance

Measured across 4 representative benchmark scenarios:

| Scenario | Status | Ideas Returned | Duration | LLM Calls | Tool Calls | Prompt Tokens | Output Tokens | Total Tokens | Cache Hits |
|---|---|---|---|---|---|---|---|---|---|
| **Healthcare AI** | `success` | 5 / 5 | 85.59s | 1 | 6 | 6,681 | 6,929 | **15,704** | 0 |
| **DevTools & Infra** | `success` | 5 / 5 | 80.77s | 1 | 5 | 6,158 | 7,530 | **15,187** | 0 |
| **Climate & Sustainability** | `success` | 5 / 5 | 56.54s | 1 | 3 | 3,790 | 5,393 | **10,505** | 0 |
| **Repeated Request (Cache Hit)** | `success_cached` | 5 / 5 | **0.01s** | 0 | 0 | 0 | 0 | **0** | 1 (100% saved) |

*Historical baseline was ~80K tokens/run. The current optimized architecture achieves **10.5K – 15.7K tokens/run** (an ~80%+ reduction in token cost).*

## Repository Structure

- `runner.py`: Primary execution pipeline wrapper.
- `streamlit_app.py`: Streamlit developer console.
- `benchmark.py`: Standard benchmark runner.
- `hackathon_intelligence/`:
  - `agent.py`: ADK Agent configuration & prompt instructions.
  - `research_tools.py`: Tavily search wrapper with limits and deduplication.
  - `research_cache.py`: SQLite search and request cache engine.
  - `ranking.py`: Weighted deterministic scoring and ranking.
  - `schemas.py`: Pydantic data models.
  - `logger.py`: Telemetry logger writing to `logs/run_logs.jsonl`.
  - `document_parser.py`: PDF extraction helpers.
- `tests/`: Unit test suite covering caching, deduplication, research limits, ranking, schemas, and observability.