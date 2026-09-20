import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

try:
    from hackathon_intelligence.document_parser import extract_text_from_pdf
    from hackathon_intelligence.observability import RunTrace
    from hackathon_intelligence.schemas import HackathonRequest
    from hackathon_intelligence.url_parser import fetch_hackathon_url, validate_url
    from runner import run_hackathon_agent
except Exception as exc:
    st.set_page_config(page_title="Hackathon Intelligence Console", layout="wide")
    st.error("Could not import hackathon intelligence modules.")
    st.code(str(exc))
    st.stop()

st.set_page_config(
    page_title="Hackathon Intelligence",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Hackathon Intelligence Agent")
st.caption("Production-shaped research agent for hackathon opportunity discovery and evaluation.")

# ---------------------------------------------------------
# Sidebar: API Key & Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.subheader("Gemini API key")
    st.markdown("[🔑 Get a Gemini API key ↗](https://aistudio.google.com/apikey)", unsafe_allow_html=True)
    
    user_api_key = st.text_input(
        "Gemini API key",
        type="password",
        placeholder="Paste your Gemini API key",
    )

    env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if user_api_key and user_api_key.strip():
        st.success("✓ Using your Gemini API key")
        effective_key = user_api_key.strip()
    elif env_key and env_key.strip():
        st.success("✓ Using configured Gemini API key")
        effective_key = env_key.strip()
    else:
        st.warning("⚠️ Add a Gemini API key to continue")
        effective_key = None

    st.divider()
    st.subheader("Agent Configuration")
    st.write("**Model:** `gemini-2.5-flash`")
    st.write("**Research Tool:** `search_web` (Tavily)")
    st.write("**Cache:** SQLite bounded cache")
    st.write("**Ranking:** Weighted Python scoring")
    st.divider()
    if st.button("Clear session state", use_container_width=True):
        for key in ["result", "trace", "run_id"]:
            st.session_state.pop(key, None)
        st.rerun()

# ---------------------------------------------------------
# Tabs
# ---------------------------------------------------------
tab_run, tab_results, tab_metrics, tab_logs = st.tabs(["🚀 Run Agent", "📋 Results & Ideas", "📊 Metrics", "📁 Run Logs"])

with tab_run:
    st.subheader("Hackathon Specification")
    
    url_input = st.text_input(
        "🔗 Hackathon URL",
        placeholder="Paste the hackathon link here...",
        help="Paste a hackathon webpage link e.g. https://example.com/hackathon"
    )

    pdf_file = st.file_uploader(
        "📄 Upload hackathon PDF",
        type=["pdf"],
        help="Upload a PDF specification document"
    )

    pasted_text = st.text_area(
        "📝 Paste hackathon description",
        value="",
        placeholder="Paste the hackathon brief or specification text...",
        height=120,
    )

    st.divider()
    col_user, col_opts = st.columns([2, 1])
    with col_user:
        user_idea = st.text_input("Optional Initial Idea / Area", placeholder="e.g. Radiology report summarizer")
    with col_opts:
        additional_context = st.text_input("Optional Constraints", placeholder="e.g. Privacy compliant workflows")
        num_ideas = st.slider("Requested Ideas (N)", min_value=1, max_value=10, value=5)

    can_run = effective_key is not None
    if not can_run:
        st.info("Please enter a valid Gemini API key in the sidebar to generate ideas.")

    if st.button("Generate ideas", type="primary", disabled=not can_run):
        primary_spec = ""
        input_source_info = ""

        # Priority 1: URL
        if url_input and url_input.strip():
            with st.spinner("Fetching hackathon details from URL..."):
                fetch_res = fetch_hackathon_url(url_input.strip())
                if fetch_res["success"]:
                    primary_spec = fetch_res["text"]
                    input_source_info = f"Using URL as primary specification source ({url_input.strip()})."
                    extra_ctx = []
                    if pdf_file:
                        try:
                            temp_pdf = PROJECT_ROOT / f"temp_{uuid.uuid4().hex}.pdf"
                            temp_pdf.write_bytes(pdf_file.getvalue())
                            pdf_text = extract_text_from_pdf(str(temp_pdf))
                            temp_pdf.unlink(missing_ok=True)
                            extra_ctx.append(f"ATTACHED PDF BRIEF:\n{pdf_text}")
                        except Exception:
                            pass
                    if pasted_text and pasted_text.strip():
                        extra_ctx.append(f"PASTED TEXT BRIEF:\n{pasted_text.strip()}")
                    if extra_ctx:
                        primary_spec += "\n\n" + "\n\n".join(extra_ctx)
                else:
                    st.warning(fetch_res["error"])
                    if pdf_file:
                        try:
                            temp_pdf = PROJECT_ROOT / f"temp_{uuid.uuid4().hex}.pdf"
                            temp_pdf.write_bytes(pdf_file.getvalue())
                            primary_spec = extract_text_from_pdf(str(temp_pdf))
                            temp_pdf.unlink(missing_ok=True)
                            input_source_info = "URL fetch failed. Fallback: using uploaded PDF."
                        except Exception:
                            pass
                    elif pasted_text and pasted_text.strip():
                        primary_spec = pasted_text.strip()
                        input_source_info = "URL fetch failed. Fallback: using pasted text."

        # Priority 2: PDF
        elif pdf_file:
            with st.spinner("Extracting text from uploaded PDF..."):
                try:
                    temp_pdf = PROJECT_ROOT / f"temp_{uuid.uuid4().hex}.pdf"
                    temp_pdf.write_bytes(pdf_file.getvalue())
                    primary_spec = extract_text_from_pdf(str(temp_pdf))
                    temp_pdf.unlink(missing_ok=True)
                    input_source_info = "Using uploaded PDF as hackathon specification source."
                    if pasted_text and pasted_text.strip():
                        primary_spec += f"\n\nPASTED TEXT BRIEF:\n{pasted_text.strip()}"
                except Exception as exc:
                    st.error(f"Could not extract text from PDF: {exc}")

        # Priority 3: Text
        elif pasted_text and pasted_text.strip():
            primary_spec = pasted_text.strip()
            input_source_info = "Using pasted description as hackathon specification source."

        if not primary_spec or len(primary_spec.strip()) < 10:
            st.error("Please provide a hackathon URL, upload a PDF, or paste a description (min 10 characters).")
        else:
            if input_source_info:
                st.info(f"ℹ️ {input_source_info}")

            req = HackathonRequest(
                hackathon_text=primary_spec,
                user_idea=user_idea.strip() if user_idea else None,
                additional_context=additional_context.strip() if additional_context else None,
                num_ideas=num_ideas,
            )
            session_id = str(uuid.uuid4())
            st.session_state["run_id"] = session_id
            
            with st.spinner("Executing bounded research & candidate evaluation..."):
                try:
                    final_set, run_trace = asyncio.run(
                        run_hackathon_agent(req, session_id=session_id, api_key=user_api_key.strip() if user_api_key else None)
                    )
                    st.session_state["result"] = final_set
                    st.session_state["trace"] = run_trace
                    st.success("Run completed successfully!")
                except Exception as exc:
                    st.error(f"Execution failed: {exc}")

# ---------------------------------------------------------
# Display Results & Engineering Observability Panel
# ---------------------------------------------------------
if "trace" in st.session_state and "result" in st.session_state:
    tr: RunTrace = st.session_state["trace"]
    res = st.session_state["result"]

    with tab_run:
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Status", tr.status)
        m_col2.metric("Duration", f"{tr.duration_ms / 1000.0:.2f}s")
        m_col3.metric("Ideas Returned", f"{len(res.ideas)} / {tr.requested_ideas}")
        m_col4.metric("Tool Calls", tr.tool_calls_count)
        m_col5.metric("Total Tokens", f"{tr.token_usage.total_tokens:,}")

        # ---------------------------------------------------------
        # Collapsible AI Engineering Trace Section
        # ---------------------------------------------------------
        with st.expander("🔬 AI engineering trace", expanded=True):

            # 1. Run Overview & Token Usage
            st.markdown("### 1. Run Overview & Token Usage")
            ov_col1, ov_col2 = st.columns(2)
            with ov_col1:
                st.write(f"**Run ID:** `{tr.run_id}`")
                st.write(f"**Model:** `{tr.model}`")
                st.write(f"**Total Duration:** `{tr.duration_ms / 1000.0:.2f}s`")
                st.write(f"**LLM Calls Count:** `{tr.token_usage.llm_calls_count}`")
                st.write(f"**Tool Calls Count:** `{tr.tool_calls_count}`")
            with ov_col2:
                st.write(f"**Input (Prompt) Tokens:** `{tr.token_usage.prompt_tokens:,}`")
                st.write(f"**Output (Candidate) Tokens:** `{tr.token_usage.output_tokens:,}`")
                st.write(f"**Total Tokens:** `{tr.token_usage.total_tokens:,}`")
                if tr.token_usage.cached_input_tokens > 0:
                    st.write(f"**Cached Input Tokens:** `{tr.token_usage.cached_input_tokens:,}`")
                st.write(f"**Ideas Requested / Returned:** `{tr.requested_ideas}` / `{tr.returned_ideas}`")

            st.divider()

            # 2. Tool-call Timeline
            st.markdown("### 2. Tool-call Timeline")
            if not tr.tool_calls:
                st.caption("No external tool calls were executed for this run.")
            else:
                for tc in tr.tool_calls:
                    badge_color = "🟢 HIT" if tc.cache_status == "HIT" else "🔴 MISS"
                    with st.container(border=True):
                        tc_c1, tc_c2 = st.columns([3, 1])
                        tc_c1.markdown(f"**#{tc.seq_num} 🔎 `{tc.tool_name}`** (Cache: {badge_color})")
                        tc_c2.caption(f"⏱️ {tc.duration_ms:.2f} ms | {tc.timestamp}")
                        
                        st.json(tc.sanitized_args)
                        st.caption(f"**Results retrieved:** {tc.result_count}")
                        if tc.compact_evidence:
                            for ev in tc.compact_evidence:
                                st.markdown(f"- **[{ev['title']}]({ev['url']})** (`{ev['domain']}`)\n  *{ev['snippet']}*")
                        if tc.error:
                            st.error(f"Tool Error: {tc.error}")

            st.divider()

            # 3. Research Trace & Caching
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                st.markdown("### 3. Research Trace")
                st.write(f"- **Searches performed:** `{tr.research_metrics.searches_performed}`")
                st.write(f"  - `search_web` calls: `{tr.research_metrics.search_web_calls}`")
                st.write(f"  - `search_github` calls: `{tr.research_metrics.search_github_calls}`")
                st.write(f"  - `search_reddit` calls: `{tr.research_metrics.search_reddit_calls}`")
                st.write(f"- **Results retrieved:** `{tr.research_metrics.results_retrieved}`")
                st.write(f"- **Duplicates removed:** `{tr.research_metrics.duplicates_removed}`")
                st.write(f"- **Sources selected:** `{tr.research_metrics.sources_selected}`")
                st.write(f"- **Cache hits:** `{tr.research_metrics.cache_hits}` | **Cache misses:** `{tr.research_metrics.cache_misses}`")

            with r_col2:
                st.markdown("### 4. ⚡ Caching Breakdown")
                if tr.cache_metrics.request_cache_hit:
                    st.success(f"⚡ Request cache HIT — 0 LLM calls, 0 search calls, 0 new tokens, Response returned in {tr.duration_ms:.2f} ms")
                else:
                    st.write(f"**Request cache:** `MISS`")
                st.write(f"**Research cache hits:** `{tr.cache_metrics.research_cache_hits}`")
                st.write(f"**Research cache misses:** `{tr.cache_metrics.research_cache_misses}`")
                st.write(f"**Search calls avoided:** `{tr.cache_metrics.search_calls_avoided}`")
                st.write(f"**Cached sources reused:** `{tr.cache_metrics.cached_sources_reused}`")
                st.write(f"**Cache hit rate:** `{tr.cache_metrics.hit_rate_pct}%`")

            st.divider()

            # 5. Agent Execution Timeline & Errors
            st.markdown("### 5. Agent Execution Timeline")
            st.caption("Major execution pipeline stages (No private chain-of-thought displayed):")
            stage_flow = []
            for stg in tr.stages:
                stage_flow.append(f"✓ **{stg.name}** ({stg.duration_ms:.2f} ms)")
            st.markdown("\n↓\n".join(stage_flow))

            st.write("")
            st.markdown("### 6. Retries & Errors")
            err_c1, err_c2, err_c3, err_c4 = st.columns(4)
            err_c1.metric("Retries", tr.errors.retries)
            err_c2.metric("Validation Failures", tr.errors.validation_failures)
            err_c3.metric("Tool Errors", tr.errors.tool_errors)
            err_c4.metric("LLM Errors", tr.errors.llm_errors)
            if tr.errors.last_error:
                st.error(f"Sanitized Error: {tr.errors.last_error}")

            st.divider()

            # 7. Final Ranking Trace
            st.markdown("### 7. Deterministic Ranking Trace")
            st.info(f"ℹ️ **Weight Mode:** {tr.ranking_metrics.weights_type}")
            st.write("**Weights used:**", tr.ranking_metrics.weights)

            for idx, item in enumerate(tr.ranking_metrics.ideas_scores, 1):
                st.write(
                    f"**#{idx} {item['title']}** — Final Weighted Score: **{item['final_score']:.2f} / 10**\n"
                    f"*(Fit: {item['hackathon_fit_score']} | Impact: {item['impact_score']} | Novelty: {item['novelty_score']} | Feasibility: {item['feasibility_score']} | Demo: {item['demoability_score']} | Research: {item['research_potential_score']})*"
                )

            st.divider()

            # 8. Export Run Trace Button
            st.markdown("### 8. Export Trace Data")
            export_json_str = tr.to_sanitized_export_json()
            st.download_button(
                label="⬇️ Export run trace",
                data=export_json_str,
                file_name=f"agent-trace-{tr.run_id}.json",
                mime="application/json",
                use_container_width=True
            )

    with tab_results:
        st.subheader("Hackathon Profile")
        st.json(res.hackathon_profile.model_dump())
        
        st.subheader("Ranked Project Ideas")
        for idx, idea in enumerate(res.ideas, 1):
            with st.expander(f"#{idx} {idea.title} — Score: {idea.score:.2f} / 10"):
                st.write(f"**One line summary:** {idea.one_line_summary}")
                st.write(f"**Target User:** {idea.target_user}")
                st.write(f"**Problem:** {idea.problem}")
                st.write(f"**Proposed Solution:** {idea.proposed_solution}")
                st.write(f"**Market Gap:** {idea.market_gap}")
                st.write(f"**Technical Novelty:** {idea.technical_novelty}")
                st.write(f"**Scores:** Fit {idea.hackathon_fit_score} | Impact {idea.impact_score} | Novelty {idea.novelty_score} | Feasibility {idea.feasibility_score} | Demo {idea.demoability_score} | Research {idea.research_potential_score}")

        st.subheader("Sources & Evidence")
        for s in res.sources:
            st.markdown(f"- **[{s.title}]({s.url})** (`{s.domain}`)\n  *{s.evidence}*")

    with tab_metrics:
        st.subheader("Structured Operational Telemetry")
        st.json(tr.model_dump())

with tab_logs:
    log_file = Path("C:/Users/tprit/PROJECTS/hackathon-agent/logs/run_logs.jsonl")
    if log_file.exists():
        st.code(log_file.read_text(encoding="utf-8")[-3000:])
    else:
        st.info("No logs created yet.")