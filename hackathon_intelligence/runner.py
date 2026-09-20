import os
import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

ENV_PATH = Path("C:/Users/tprit/PROJECTS/hackathon-agent/.env")
load_dotenv(ENV_PATH)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from hackathon_intelligence.agent import root_agent
from hackathon_intelligence.logger import log_run
from hackathon_intelligence.observability import RunTrace
from hackathon_intelligence.ranking import rank_ideas, parse_weights, DEFAULT_WEIGHTS
from hackathon_intelligence.research_cache import (
    get_request_cache,
    metrics as cache_metrics,
    set_request_cache,
)
from hackathon_intelligence.research_tools import tracker as research_tracker
from hackathon_intelligence.schemas import FinalIdeaSet, HackathonRequest


def resolve_api_key(user_key: Optional[str] = None) -> str:
    """
    Resolves API key with priority:
    1. User-provided key from caller / UI
    2. GEMINI_API_KEY / GOOGLE_API_KEY from environment
    """
    if user_key and user_key.strip():
        return user_key.strip()
    
    env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    raise ValueError("No Gemini API key available. Please provide a key in the UI or set GEMINI_API_KEY in environment.")


def extract_and_repair_json(raw_text: str) -> dict:
    """
    Extracts and repairs JSON output from agent text, handling markdown fences,
    unclosed strings/brackets from token truncation, and trailing commas.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty output text returned from agent.")

    text = raw_text.strip()
    
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start_idx = text.find("{")
    if start_idx == -1:
        raise ValueError("No JSON object starting with '{' found in agent response.")

    text = text[start_idx:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    end_idx = text.rfind("}")
    if end_idx != -1:
        candidate = text[:end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    repaired = text
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

    in_string = False
    escape = False
    for char in repaired:
        if char == '"' and not escape:
            in_string = not in_string
        escape = (char == '\\' and not escape)
    
    if in_string:
        repaired += '"'

    repaired = re.sub(r',\s*"[^"]*"?\s*:?\s*$', '', repaired)
    repaired = re.sub(r',\s*$', '', repaired)

    stack = []
    in_str = False
    esc = False
    for ch in repaired:
        if ch == '"' and not esc:
            in_str = not in_str
        esc = (ch == '\\' and not esc)
        if not in_str:
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

    close_map = {'{': '}', '[': ']'}
    while stack:
        repaired += close_map[stack.pop()]

    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

    return json.loads(repaired)


async def run_hackathon_agent(
    request: HackathonRequest,
    session_id: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 2
) -> Tuple[FinalIdeaSet, RunTrace]:
    """
    Primary execution function for Hackathon Intelligence.
    Populates structured RunTrace observability model during execution.
    """
    start_time = time.perf_counter()
    run_id = session_id or str(uuid.uuid4())

    run_trace = RunTrace(
        run_id=run_id,
        model=root_agent.model or "gemini-2.5-flash",
        requested_ideas=request.num_ideas,
    )

    effective_key = resolve_api_key(api_key)
    
    orig_gemini_key = os.environ.get("GEMINI_API_KEY")
    orig_google_key = os.environ.get("GOOGLE_API_KEY")

    os.environ["GEMINI_API_KEY"] = effective_key
    os.environ["GOOGLE_API_KEY"] = effective_key

    # Stage 1: Request received
    t_stage = time.perf_counter()
    run_trace.record_stage("Request received", (time.perf_counter() - t_stage) * 1000.0)

    try:
        # 1. Request-level Cache Check
        t_stage = time.perf_counter()
        cached_response = get_request_cache(
            hackathon_text=request.hackathon_text,
            user_idea=request.user_idea,
            additional_context=request.additional_context,
            num_ideas=request.num_ideas,
        )

        if cached_response is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            try:
                final_set = FinalIdeaSet.model_validate(cached_response)
                run_trace.status = "success_cached"
                run_trace.duration_ms = duration_ms
                run_trace.returned_ideas = len(final_set.ideas)
                run_trace.cache_metrics.request_cache_hit = True
                run_trace.record_stage("Hackathon specification parsed", (time.perf_counter() - t_stage) * 1000.0)
                run_trace.record_stage("Cached result retrieved", duration_ms)

                log_run(
                    run_id=run_id,
                    status="success_cached",
                    duration_ms=duration_ms,
                    requested_ideas=request.num_ideas,
                    returned_ideas=len(final_set.ideas),
                    llm_calls=0,
                    tool_calls=0,
                    cache_hits=cache_metrics.request_hits,
                    cache_misses=cache_metrics.request_misses,
                    search_calls=0,
                    sources_retrieved=0,
                    sources_deduplicated=0,
                    sources_selected=len(final_set.sources),
                    prompt_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    retries=0,
                    validation_failures=0,
                )
                return final_set, run_trace
            except Exception:
                pass

        run_trace.cache_metrics.request_cache_hit = False

        # Reset research tracker with active trace
        research_tracker.reset(trace=run_trace)

        # Stage 2: Hackathon specification parsed
        run_trace.record_stage("Hackathon specification parsed", (time.perf_counter() - t_stage) * 1000.0)

        # Stage 3: Research planned
        t_stage = time.perf_counter()
        run_trace.record_stage("Research planned", (time.perf_counter() - t_stage) * 1000.0)

        # Formulate Prompt
        prompt_parts = [
            f"HACKATHON SPECIFICATION:\n{request.hackathon_text}\n",
            f"REQUESTED NUMBER OF IDEAS: {request.num_ideas}\n",
        ]
        if request.user_idea:
            prompt_parts.append(f"USER INITIAL IDEA / AREA: {request.user_idea}\n")
        if request.additional_context:
            prompt_parts.append(f"ADDITIONAL CONSTRAINTS / CONTEXT: {request.additional_context}\n")

        user_prompt = "\n".join(prompt_parts)

        app_name = "hackathon_intelligence"
        user_id = "developer"
        session_service = InMemorySessionService()

        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=run_id,
        )

        runner = Runner(
            app_name=app_name,
            agent=root_agent,
            session_service=session_service,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=user_prompt)]
        )

        final_idea_set: Optional[FinalIdeaSet] = None
        last_error: Optional[str] = None

        t_research = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                events = []
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=run_id,
                    new_message=message,
                ):
                    events.append(event)

                    # Accumulate token usage (SUM across LLM calls)
                    usage = getattr(event, "usage_metadata", None)
                    if usage:
                        p_tok = getattr(usage, "prompt_token_count", 0) or getattr(usage, "input_token_count", 0) or 0
                        o_tok = getattr(usage, "candidates_token_count", 0) or getattr(usage, "output_token_count", 0) or 0
                        t_tok = getattr(usage, "total_token_count", 0) or (p_tok + o_tok)
                        c_tok = getattr(usage, "cached_content_token_count", 0) or 0
                        if t_tok > 0:
                            run_trace.token_usage.accumulate(p_tok, o_tok, t_tok, c_tok)

                # Stage 4: Web research
                run_trace.record_stage("Web research", (time.perf_counter() - t_research) * 1000.0)

                # Stage 5: Evidence deduplicated
                t_stage = time.perf_counter()
                run_trace.record_stage("Evidence deduplicated", (time.perf_counter() - t_stage) * 1000.0)

                # Stage 6: Opportunity space synthesized
                t_stage = time.perf_counter()
                run_trace.record_stage("Opportunity space synthesized", (time.perf_counter() - t_stage) * 1000.0)

                # Extract raw output text
                raw_text = ""
                for ev in reversed(events):
                    cnt = getattr(ev, "content", None)
                    pts = getattr(cnt, "parts", None) or []
                    for pt in pts:
                        txt = getattr(pt, "text", "")
                        if txt and txt.strip():
                            raw_text = txt.strip()
                            break
                    if raw_text:
                        break

                if not raw_text:
                    raise ValueError("No text output returned from agent run.")

                # Stage 7: Candidate ideas generated
                t_stage = time.perf_counter()
                run_trace.record_stage("Candidate ideas generated", (time.perf_counter() - t_stage) * 1000.0)

                # Extract & repair JSON
                parsed_dict = extract_and_repair_json(raw_text)
                final_idea_set = FinalIdeaSet.model_validate(parsed_dict)
                break

            except Exception as exc:
                run_trace.errors.retries = attempt
                last_error = str(exc)
                run_trace.errors.validation_failures += 1
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))
                else:
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        run_trace.duration_ms = duration_ms

        if final_idea_set is None:
            run_trace.status = "error"
            run_trace.errors.last_error = last_error
            log_run(
                run_id=run_id,
                status="error",
                duration_ms=duration_ms,
                requested_ideas=request.num_ideas,
                returned_ideas=0,
                llm_calls=run_trace.token_usage.llm_calls_count,
                tool_calls=run_trace.tool_calls_count,
                cache_hits=cache_metrics.search_hits,
                cache_misses=cache_metrics.search_misses,
                search_calls=research_tracker.search_calls,
                sources_retrieved=research_tracker.sources_retrieved,
                sources_deduplicated=research_tracker.sources_deduplicated,
                sources_selected=research_tracker.sources_selected,
                prompt_tokens=run_trace.token_usage.prompt_tokens,
                output_tokens=run_trace.token_usage.output_tokens,
                total_tokens=run_trace.token_usage.total_tokens,
                retries=run_trace.errors.retries,
                validation_failures=run_trace.errors.validation_failures,
                error=last_error or "Failed to generate valid output",
            )
            raise RuntimeError(f"Agent execution failed: {last_error}")

        # Stage 8: Candidates filtered & ranked
        t_stage = time.perf_counter()
        run_trace.record_stage("Candidates filtered", (time.perf_counter() - t_stage) * 1000.0)

        t_rank = time.perf_counter()
        weights_dict = parse_weights(final_idea_set.hackathon_profile)
        is_official = (final_idea_set.hackathon_profile and len(final_idea_set.hackathon_profile.judging_weights) > 0)
        
        run_trace.ranking_metrics.weights_type = (
            "Using official hackathon judging weights" if is_official else "Using fallback ranking weights"
        )
        run_trace.ranking_metrics.weights = weights_dict

        # Perform deterministic Python ranking
        final_idea_set.ideas = rank_ideas(
            ideas=final_idea_set.ideas,
            profile=final_idea_set.hackathon_profile,
            requested_count=request.num_ideas,
        )

        for idea in final_idea_set.ideas:
            run_trace.ranking_metrics.ideas_scores.append({
                "title": idea.title,
                "hackathon_fit_score": idea.hackathon_fit_score,
                "impact_score": idea.impact_score,
                "novelty_score": idea.novelty_score,
                "feasibility_score": idea.feasibility_score,
                "demoability_score": idea.demoability_score,
                "research_potential_score": idea.research_potential_score,
                "final_score": idea.score or 0.0,
            })

        run_trace.record_stage("Ideas ranked", (time.perf_counter() - t_rank) * 1000.0)

        # Stage 9: Final response validated
        t_stage = time.perf_counter()
        run_trace.record_stage("Final response validated", (time.perf_counter() - t_stage) * 1000.0)

        # Update trace telemetry metrics
        run_trace.status = "success"
        run_trace.returned_ideas = len(final_idea_set.ideas)
        
        run_trace.research_metrics.searches_performed = research_tracker.search_calls
        run_trace.research_metrics.results_retrieved = research_tracker.sources_retrieved
        run_trace.research_metrics.duplicates_removed = research_tracker.sources_deduplicated
        run_trace.research_metrics.sources_selected = research_tracker.sources_selected
        run_trace.research_metrics.cache_hits = cache_metrics.search_hits
        run_trace.research_metrics.cache_misses = cache_metrics.search_misses

        run_trace.cache_metrics.research_cache_hits = cache_metrics.search_hits
        run_trace.cache_metrics.research_cache_misses = cache_metrics.search_misses
        run_trace.cache_metrics.search_calls_avoided = cache_metrics.search_hits
        run_trace.cache_metrics.cached_sources_reused = research_tracker.sources_selected if cache_metrics.search_hits > 0 else 0
        total_cache_ops = cache_metrics.search_hits + cache_metrics.search_misses
        run_trace.cache_metrics.hit_rate_pct = round((cache_metrics.search_hits / total_cache_ops * 100.0), 1) if total_cache_ops > 0 else 0.0

        # Save to Request Cache
        set_request_cache(
            hackathon_text=request.hackathon_text,
            user_idea=request.user_idea,
            additional_context=request.additional_context,
            num_ideas=request.num_ideas,
            result_data=final_idea_set.model_dump(exclude_none=True),
        )

        # Structured Logging
        log_run(
            run_id=run_id,
            status="success",
            duration_ms=duration_ms,
            requested_ideas=request.num_ideas,
            returned_ideas=len(final_idea_set.ideas),
            llm_calls=run_trace.token_usage.llm_calls_count or 1,
            tool_calls=run_trace.tool_calls_count,
            cache_hits=cache_metrics.search_hits,
            cache_misses=cache_metrics.search_misses,
            search_calls=research_tracker.search_calls,
            sources_retrieved=research_tracker.sources_retrieved,
            sources_deduplicated=research_tracker.sources_deduplicated,
            sources_selected=research_tracker.sources_selected,
            prompt_tokens=run_trace.token_usage.prompt_tokens,
            output_tokens=run_trace.token_usage.output_tokens,
            total_tokens=run_trace.token_usage.total_tokens,
            retries=run_trace.errors.retries,
            validation_failures=run_trace.errors.validation_failures,
        )

        return final_idea_set, run_trace

    finally:
        if orig_gemini_key is not None:
            os.environ["GEMINI_API_KEY"] = orig_gemini_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

        if orig_google_key is not None:
            os.environ["GOOGLE_API_KEY"] = orig_google_key
        else:
            os.environ.pop("GOOGLE_API_KEY", None)


def run_hackathon_agent_sync(
    request: HackathonRequest,
    session_id: Optional[str] = None,
    api_key: Optional[str] = None
) -> Tuple[FinalIdeaSet, RunTrace]:
    return asyncio.run(run_hackathon_agent(request, session_id=session_id, api_key=api_key))