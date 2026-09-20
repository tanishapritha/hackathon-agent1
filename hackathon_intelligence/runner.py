import os
import asyncio
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from .config import (
    ENV_PATH,
    GEMINI_MODEL,
    OPENAI_MODEL,
    OPENROUTER_MODEL,
    MAX_LLM_CALLS,
    MAX_SEARCH_CALLS,
    MAX_RESULTS_PER_SEARCH,
)
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

from google.genai import client as genai_client
from google.genai import types

from .agent import (
    PLANNER_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
    CANDIDATE_INSTRUCTIONS,
)
from .logger import log_run
from .observability import RunTrace, RunTraceEvent
from .ranking import rank_ideas, parse_weights
from .research_cache import (
    get_request_cache,
    metrics as cache_metrics,
    set_request_cache,
)
from .research_tools import tracker as research_tracker, search_web_batch
from .schemas import (
    CandidateIdea,
    FinalIdeaSet,
    HackathonProfile,
    HackathonRequest,
    OpportunityMap,
    ResearchSource,
)


PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
}


def normalize_provider(provider: Optional[str]) -> str:
    provider_id = (provider or "gemini").strip().lower()
    if provider_id not in PROVIDER_LABELS:
        raise ValueError(f"Unsupported model provider: {provider}")
    return provider_id


def default_model_for_provider(provider: str) -> str:
    provider_id = normalize_provider(provider)
    if provider_id == "openrouter":
        return OPENROUTER_MODEL
    if provider_id == "openai":
        return OPENAI_MODEL
    return GEMINI_MODEL


def resolve_api_key(user_key: Optional[str] = None, provider: str = "gemini") -> str:
    """
    Resolves API key with priority:
    1. User-provided key from caller / UI
    2. GEMINI_API_KEY / GOOGLE_API_KEY from environment
    """
    if user_key and user_key.strip():
        return user_key.strip()
    
    provider_id = normalize_provider(provider)
    if provider_id == "openrouter":
        env_key = os.getenv("OPENROUTER_API_KEY")
        provider_name = "OpenRouter"
    elif provider_id == "openai":
        env_key = os.getenv("OPENAI_API_KEY")
        provider_name = "OpenAI"
    else:
        env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        provider_name = "Gemini"

    if env_key and env_key.strip():
        return env_key.strip()

    raise ValueError(f"No {provider_name} API key available. Please provide a key in the UI or set it in Streamlit secrets/environment.")


def extract_and_repair_json(raw_text: str) -> dict:
    """
    Extracts and repairs JSON output from agent text, handling markdown fences,
    unclosed strings/brackets from token truncation, and trailing commas.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty output text returned from model.")

    text = raw_text.strip()
    
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start_idx = text.find("{")
    if start_idx == -1:
        raise ValueError("No JSON object starting with '{' found in model response.")

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


async def call_gemini_step(
    client: genai_client.Client,
    model_name: str,
    instructions: str,
    prompt: str,
    step_num: int,
    purpose: str,
    run_trace: RunTrace,
    max_retries: int = 3,
) -> Tuple[dict, RunTraceEvent]:
    """Execute a single controlled Gemini LLM step with 503 retry backoff."""
    if run_trace.token_usage.llm_calls_count >= MAX_LLM_CALLS:
        raise RuntimeError(f"LLM call limit reached ({MAX_LLM_CALLS} calls). Cannot execute further calls.")

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    system_instruction=instructions,
                    temperature=0.3,
                    response_mime_type="application/json",
                )
            )

            dur_ms = (time.perf_counter() - t0) * 1000.0

            p_tok = 0
            o_tok = 0
            t_tok = 0
            c_tok = 0
            usage = getattr(response, "usage_metadata", None)
            if usage:
                p_tok = getattr(usage, "prompt_token_count", 0) or getattr(usage, "input_token_count", 0) or 0
                o_tok = getattr(usage, "candidates_token_count", 0) or getattr(usage, "output_token_count", 0) or 0
                t_tok = getattr(usage, "total_token_count", 0) or (p_tok + o_tok)
                c_tok = getattr(usage, "cached_content_token_count", 0) or 0

            event = run_trace.record_llm_call(
                call_num=step_num,
                prompt_tokens=p_tok,
                output_tokens=o_tok,
                total_tokens=t_tok,
                duration_ms=dur_ms,
                purpose=purpose
            )

            raw_text = response.text or ""
            parsed_dict = extract_and_repair_json(raw_text)
            return parsed_dict, event

        except Exception as exc:
            dur_ms = (time.perf_counter() - t0) * 1000.0
            err_msg = str(exc)
            last_exc = exc

            # Never retry quota exhaustion
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                clean_err = "⚠️ Gemini quota reached. Free tier request quota exhausted."
                run_trace.errors.llm_errors += 1
                run_trace.errors.last_error = clean_err
                raise RuntimeError(clean_err)

            # Never retry model not found
            if "404" in err_msg or "NOT_FOUND" in err_msg or "models/" in err_msg:
                clean_err = f"Configured Gemini model '{model_name}' is unavailable."
                run_trace.errors.llm_errors += 1
                run_trace.errors.last_error = clean_err
                raise RuntimeError(clean_err)

            # Retry on 503 transient overload
            is_503 = "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower()
            if is_503 and attempt < max_retries:
                backoff_s = 5.0 * (2 ** attempt)  # 5s, 10s, 20s
                run_trace.errors.retries += 1
                await asyncio.sleep(backoff_s)
                continue

            run_trace.errors.llm_errors += 1
            run_trace.errors.last_error = err_msg
            raise exc

    # Should not reach here
    run_trace.errors.llm_errors += 1
    raise last_exc  # type: ignore[misc]


def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc


async def call_openai_compatible_step(
    provider: str,
    api_key: str,
    model_name: str,
    instructions: str,
    prompt: str,
    step_num: int,
    purpose: str,
    run_trace: RunTrace,
    max_retries: int = 3,
) -> Tuple[dict, RunTraceEvent]:
    """Execute a JSON LLM step against OpenRouter/OpenAI-compatible chat completions."""
    if run_trace.token_usage.llm_calls_count >= MAX_LLM_CALLS:
        raise RuntimeError(f"LLM call limit reached ({MAX_LLM_CALLS} calls). Cannot execute further calls.")

    provider_id = normalize_provider(provider)
    if provider_id == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hackathon-intelligence.streamlit.app",
            "X-Title": "Hackathon Intelligence",
        }
    elif provider_id == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        raise ValueError(f"Unsupported OpenAI-compatible provider: {provider}")

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            response = await asyncio.to_thread(_post_json, url, headers, payload)
            dur_ms = (time.perf_counter() - t0) * 1000.0

            usage = response.get("usage") or {}
            p_tok = int(usage.get("prompt_tokens") or 0)
            o_tok = int(usage.get("completion_tokens") or 0)
            t_tok = int(usage.get("total_tokens") or (p_tok + o_tok))

            event = run_trace.record_llm_call(
                call_num=step_num,
                prompt_tokens=p_tok,
                output_tokens=o_tok,
                total_tokens=t_tok,
                duration_ms=dur_ms,
                purpose=purpose,
            )

            choices = response.get("choices") or []
            if not choices:
                raise ValueError("Model response did not include choices.")
            raw_text = ((choices[0].get("message") or {}).get("content") or "").strip()
            parsed_dict = extract_and_repair_json(raw_text)
            return parsed_dict, event

        except Exception as exc:
            err_msg = str(exc)
            last_exc = exc

            if "429" in err_msg or "quota" in err_msg.lower() or "insufficient" in err_msg.lower():
                clean_err = f"{PROVIDER_LABELS[provider_id]} quota or credit limit reached."
                run_trace.errors.llm_errors += 1
                run_trace.errors.last_error = clean_err
                raise RuntimeError(clean_err) from exc

            is_transient = any(marker in err_msg.lower() for marker in ["503", "502", "504", "timeout", "temporarily", "overloaded", "unavailable"])
            if is_transient and attempt < max_retries:
                run_trace.errors.retries += 1
                await asyncio.sleep(4.0 * (2 ** attempt))
                continue

            run_trace.errors.llm_errors += 1
            run_trace.errors.last_error = err_msg
            raise exc

    run_trace.errors.llm_errors += 1
    raise last_exc  # type: ignore[misc]


async def call_llm_step(
    provider: str,
    api_key: str,
    gemini_client: Optional[genai_client.Client],
    model_name: str,
    instructions: str,
    prompt: str,
    step_num: int,
    purpose: str,
    run_trace: RunTrace,
    max_retries: int = 3,
) -> Tuple[dict, RunTraceEvent]:
    provider_id = normalize_provider(provider)
    if provider_id == "gemini":
        if gemini_client is None:
            raise ValueError("Gemini client is required for Gemini provider.")
        return await call_gemini_step(
            client=gemini_client,
            model_name=model_name,
            instructions=instructions,
            prompt=prompt,
            step_num=step_num,
            purpose=purpose,
            run_trace=run_trace,
            max_retries=max_retries,
        )

    return await call_openai_compatible_step(
        provider=provider_id,
        api_key=api_key,
        model_name=model_name,
        instructions=instructions,
        prompt=prompt,
        step_num=step_num,
        purpose=purpose,
        run_trace=run_trace,
        max_retries=max_retries,
    )



async def stream_hackathon_agent(
    request: HackathonRequest,
    session_id: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 2,
    model_name: Optional[str] = None,
    provider: str = "gemini",
) -> AsyncGenerator[Tuple[RunTraceEvent, Optional[FinalIdeaSet], Optional[RunTrace]], None]:
    """
    Controlled 3-Step Pipeline Stream Generator.
    Yields live RunTraceEvent objects as events happen.
    """
    start_time = time.perf_counter()
    run_id = session_id or str(uuid.uuid4())
    provider_id = normalize_provider(provider)
    selected_model = (model_name or default_model_for_provider(provider_id)).strip() or default_model_for_provider(provider_id)

    run_trace = RunTrace(
        run_id=run_id,
        model=f"{PROVIDER_LABELS[provider_id]}:{selected_model}",
        requested_ideas=request.num_ideas,
    )

    effective_key = resolve_api_key(api_key, provider=provider_id)
    
    orig_gemini_key = os.environ.get("GEMINI_API_KEY")
    orig_google_key = os.environ.get("GOOGLE_API_KEY")

    os.environ["GEMINI_API_KEY"] = effective_key
    os.environ["GOOGLE_API_KEY"] = effective_key

    # Stage 1: Request received
    t_stage = time.perf_counter()
    ev_req = run_trace.record_stage("Request received", (time.perf_counter() - t_stage) * 1000.0)
    yield (ev_req, None, None)

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
                
                ev_spec = run_trace.record_stage("Hackathon specification parsed", (time.perf_counter() - t_stage) * 1000.0)
                yield (ev_spec, None, None)

                ev_hit = RunTraceEvent(
                    type="cache_hit",
                    timestamp=time.strftime("%H:%M:%S"),
                    cache_status="HIT",
                    message=f"⚡ Request cache HIT — 0 LLM calls, 0 search calls, 0 new tokens, Response returned in {duration_ms:.2f} ms"
                )
                yield (ev_hit, None, None)

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
                    model=f"{PROVIDER_LABELS[provider_id]}:{selected_model}"
                )
                ev_comp = run_trace.record_stage("Complete", duration_ms)
                yield (ev_comp, final_set, run_trace)
                return
            except Exception:
                pass

        run_trace.cache_metrics.request_cache_hit = False

        # Event Callback queue for live tools
        event_queue = asyncio.Queue()

        def live_tool_callback(ev: RunTraceEvent):
            try:
                event_queue.put_nowait(ev)
            except Exception:
                pass

        research_tracker.reset(trace=run_trace, event_callback=live_tool_callback)

        ev_spec = run_trace.record_stage("Hackathon specification parsed", (time.perf_counter() - t_stage) * 1000.0)
        yield (ev_spec, None, None)

        client = genai_client.Client(api_key=effective_key) if provider_id == "gemini" else None

        # ---------------------------------------------------------
        # GEMINI CALL #1: Research Planner
        # ---------------------------------------------------------
        ev_plan = run_trace.record_stage("Research planned")
        yield (ev_plan, None, None)

        planner_prompt = (
            f"HACKATHON SPECIFICATION:\n{request.hackathon_text}\n\n"
            f"USER INITIAL IDEA: {request.user_idea or 'None'}\n"
            f"CONSTRAINTS: {request.additional_context or 'None'}\n"
        )

        plan_dict, ev_llm1 = await call_llm_step(
            provider=provider_id,
            api_key=effective_key,
            gemini_client=client,
            model_name=selected_model,
            instructions=PLANNER_INSTRUCTIONS,
            prompt=planner_prompt,
            step_num=1,
            purpose="Planning research & extracting profile",
            run_trace=run_trace
        )
        yield (ev_llm1, None, None)

        hackathon_profile_dict = plan_dict.get("hackathon_profile", {})
        hackathon_profile = HackathonProfile.model_validate(hackathon_profile_dict)
        queries = plan_dict.get("research_queries", [])[:MAX_SEARCH_CALLS]

        if not queries:
            queries = [
                f"{request.user_idea or 'hackathon'} target users and pain points",
                f"{request.user_idea or 'hackathon'} existing solutions and competitors"
            ]

        # ---------------------------------------------------------
        # PYTHON RESEARCH EXECUTION (0 Gemini Calls!)
        # ---------------------------------------------------------
        ev_res_start = run_trace.record_stage("Web research")
        yield (ev_res_start, None, None)

        # Execute searches in Python
        search_results_batch = search_web_batch(queries, max_results=MAX_RESULTS_PER_SEARCH)

        # Flush any live tool call events
        while not event_queue.empty():
            ev_tool = event_queue.get_nowait()
            yield (ev_tool, None, None)

        ev_dedupe = run_trace.record_stage("Evidence deduplicated")
        yield (ev_dedupe, None, None)

        # Build compact evidence block for Gemini Call #2
        compact_sources_list = []
        evidence_text_blocks = []
        for res_batch in search_results_batch:
            for item in res_batch.get("results", [])[:MAX_RESULTS_PER_SEARCH]:
                s_id = f"S{len(compact_sources_list) + 1}"
                source_obj = ResearchSource(
                    id=s_id,
                    title=item.get("title", "Source"),
                    url=item.get("url", "https://example.com"),
                    domain=item.get("domain", "web"),
                    evidence=item.get("snippet", "")
                )
                compact_sources_list.append(source_obj)
                evidence_text_blocks.append(f"[{s_id}] {source_obj.title} ({source_obj.domain})\nEvidence: {source_obj.evidence}\nURL: {source_obj.url}")

        evidence_text = "\n\n".join(evidence_text_blocks[:15])

        # ---------------------------------------------------------
        # GEMINI CALL #2: Opportunity Synthesis
        # ---------------------------------------------------------
        ev_syn_start = run_trace.record_stage("Opportunity space synthesized")
        yield (ev_syn_start, None, None)

        synthesis_prompt = (
            f"HACKATHON PROFILE:\n{hackathon_profile.model_dump_json()}\n\n"
            f"COMPACT RESEARCH EVIDENCE:\n{evidence_text}\n\n"
            f"USER INITIAL IDEA: {request.user_idea or 'None'}\n"
        )

        synth_dict, ev_llm2 = await call_llm_step(
            provider=provider_id,
            api_key=effective_key,
            gemini_client=client,
            model_name=selected_model,
            instructions=SYNTHESIS_INSTRUCTIONS,
            prompt=synthesis_prompt,
            step_num=2,
            purpose="Synthesizing opportunity space",
            run_trace=run_trace
        )
        yield (ev_llm2, None, None)

        opportunity_map = OpportunityMap.model_validate(synth_dict)

        # ---------------------------------------------------------
        # GEMINI CALL #3: Candidate Generation & Self-Critique
        # ---------------------------------------------------------
        ev_gen_start = run_trace.record_stage("Candidate ideas generated")
        yield (ev_gen_start, None, None)

        candidate_prompt = (
            f"HACKATHON PROFILE:\n{hackathon_profile.model_dump_json()}\n\n"
            f"OPPORTUNITY MAP:\n{opportunity_map.model_dump_json()}\n\n"
            f"REQUESTED NUMBER OF IDEAS: {request.num_ideas}\n"
            f"USER INITIAL IDEA: {request.user_idea or 'None'}\n"
            f"CONSTRAINTS: {request.additional_context or 'None'}\n"
        )

        final_dict, ev_llm3 = await call_llm_step(
            provider=provider_id,
            api_key=effective_key,
            gemini_client=client,
            model_name=selected_model,
            instructions=CANDIDATE_INSTRUCTIONS,
            prompt=candidate_prompt,
            step_num=3,
            purpose="Candidate generation & self-critique",
            run_trace=run_trace
        )
        yield (ev_llm3, None, None)

        # Parse FinalIdeaSet
        final_idea_set = FinalIdeaSet.model_validate(final_dict)
        final_idea_set.hackathon_profile = hackathon_profile
        final_idea_set.opportunity_map = opportunity_map
        if not final_idea_set.sources:
            final_idea_set.sources = compact_sources_list

        # ---------------------------------------------------------
        # PYTHON DETERMINISTIC RANKING & EXACT COUNT SELECTION
        # ---------------------------------------------------------
        ev_filt = run_trace.record_stage("Candidates filtered")
        yield (ev_filt, None, None)

        t_rank = time.perf_counter()
        weights_dict = parse_weights(hackathon_profile)
        is_official = (hackathon_profile and len(hackathon_profile.judging_weights) > 0)
        
        run_trace.ranking_metrics.weights_type = (
            "Using official hackathon judging weights" if is_official else "Using fallback ranking weights"
        )
        run_trace.ranking_metrics.weights = weights_dict

        # Python ranking
        final_idea_set.ideas = rank_ideas(
            ideas=final_idea_set.ideas,
            profile=hackathon_profile,
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

        ev_rank = run_trace.record_stage("Ideas ranked", (time.perf_counter() - t_rank) * 1000.0)
        yield (ev_rank, None, None)

        ev_val = run_trace.record_stage("Final response validated")
        yield (ev_val, None, None)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        run_trace.status = "success"
        run_trace.duration_ms = duration_ms
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

        # Log completion
        log_run(
            run_id=run_id,
            status="success",
            duration_ms=duration_ms,
            requested_ideas=request.num_ideas,
            returned_ideas=len(final_idea_set.ideas),
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
            model=f"{PROVIDER_LABELS[provider_id]}:{selected_model}"
        )

        ev_complete = run_trace.record_stage("Complete", duration_ms)
        yield (ev_complete, final_idea_set, run_trace)

    finally:
        if orig_gemini_key is not None:
            os.environ["GEMINI_API_KEY"] = orig_gemini_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

        if orig_google_key is not None:
            os.environ["GOOGLE_API_KEY"] = orig_google_key
        else:
            os.environ.pop("GOOGLE_API_KEY", None)


async def run_hackathon_agent(
    request: HackathonRequest,
    session_id: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 2,
    model_name: Optional[str] = None,
    provider: str = "gemini",
) -> Tuple[FinalIdeaSet, RunTrace]:
    """Non-streaming async execution wrapper."""
    final_set = None
    run_trace = None
    async for _, res_set, trace in stream_hackathon_agent(
        request,
        session_id=session_id,
        api_key=api_key,
        max_retries=max_retries,
        model_name=model_name,
        provider=provider,
    ):
        if res_set is not None:
            final_set = res_set
        if trace is not None:
            run_trace = trace
    if final_set is None or run_trace is None:
        raise RuntimeError("Agent stream completed without returning final output.")
    return final_set, run_trace


def run_hackathon_agent_sync(
    request: HackathonRequest,
    session_id: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    provider: str = "gemini",
) -> Tuple[FinalIdeaSet, RunTrace]:
    return asyncio.run(run_hackathon_agent(request, session_id=session_id, api_key=api_key, model_name=model_name, provider=provider))
