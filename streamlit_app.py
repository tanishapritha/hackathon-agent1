import asyncio
import json
import os
import re
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
    from hackathon_intelligence.config import GEMINI_MODEL
    from hackathon_intelligence.document_parser import extract_text_from_pdf
    from hackathon_intelligence.observability import RunTrace, RunTraceEvent
    from hackathon_intelligence.schemas import HackathonRequest
    from hackathon_intelligence.url_parser import fetch_hackathon_url, validate_url
    from hackathon_intelligence.runner import stream_hackathon_agent
except Exception as exc:
    st.set_page_config(page_title="Hackathon Intelligence Console", layout="wide")
    st.error("Could not import hackathon intelligence modules.")
    st.code(str(exc))
    st.stop()

st.set_page_config(
    page_title="Hackathon Intelligence",
    page_icon="HI",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --hi-bg: #080b12;
        --hi-panel: #101622;
        --hi-panel-2: #151d2b;
        --hi-border: #263244;
        --hi-muted: #9aa7b8;
        --hi-text: #edf2f7;
        --hi-soft: #cbd5e1;
        --hi-accent: #6ea8fe;
        --hi-accent-2: #7dd3fc;
        --hi-success: #33d69f;
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(110, 168, 254, 0.12), transparent 28rem),
            linear-gradient(180deg, #080b12 0%, #0b1019 100%);
        color: var(--hi-text);
    }
    .block-container {
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        max-width: 1120px;
    }
    h1, h2, h3 {
        letter-spacing: 0;
        color: var(--hi-text);
    }
    h1 {
        font-size: 2.35rem;
        line-height: 1.1;
    }
    p, label, span, div {
        color: inherit;
    }
    div[data-testid="stMetric"] {
        background: rgba(16, 22, 34, 0.88);
        border: 1px solid var(--hi-border);
        border-radius: 8px;
        padding: 0.8rem 0.9rem;
    }
    div[data-testid="stMetric"] label {
        color: var(--hi-muted);
    }
    div[data-testid="stTabs"] button {
        font-weight: 600;
        color: var(--hi-soft);
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--hi-accent-2);
        border-bottom-color: var(--hi-accent-2);
    }
    section[data-testid="stSidebar"] {
        background: #0b1019;
        border-right: 1px solid var(--hi-border);
    }
    section[data-testid="stSidebar"] * {
        color: var(--hi-soft);
    }
    input, textarea, div[data-baseweb="select"] > div {
        background-color: #0d1420 !important;
        color: var(--hi-text) !important;
        border-color: var(--hi-border) !important;
    }
    div[data-testid="stFileUploader"] section {
        background-color: rgba(16, 22, 34, 0.82);
        border-color: var(--hi-border);
    }
    div[data-testid="stAlert"] {
        border-radius: 8px;
    }
    div[data-testid="stExpander"] {
        background: rgba(16, 22, 34, 0.72);
        border: 1px solid var(--hi-border);
        border-radius: 8px;
    }
    code, pre {
        background: #0a0f18 !important;
        color: #dbeafe !important;
        border: 1px solid var(--hi-border);
    }
    .hi-page-kicker {
        color: var(--hi-accent-2);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    .hi-page-caption {
        color: var(--hi-muted);
        font-size: 1rem;
        max-width: 780px;
        margin-top: -0.2rem;
        margin-bottom: 1.6rem;
    }
    .hi-panel {
        background: linear-gradient(180deg, rgba(21, 29, 43, 0.95), rgba(16, 22, 34, 0.95));
        border: 1px solid var(--hi-border);
        border-radius: 8px;
        padding: 1rem 1.05rem;
        margin: 0.45rem 0 1rem;
        box-shadow: 0 14px 42px rgba(0, 0, 0, 0.18);
    }
    .hi-step {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.45rem;
        height: 1.45rem;
        margin-right: 0.45rem;
        border-radius: 999px;
        background: rgba(110, 168, 254, 0.18);
        border: 1px solid rgba(110, 168, 254, 0.55);
        color: #bfdbfe;
        font-size: 0.8rem;
        font-weight: 700;
    }
    .hi-muted {
        color: var(--hi-muted);
    }
    .hi-surface {
        background: rgba(16, 22, 34, 0.74);
        border: 1px solid var(--hi-border);
        border-radius: 8px;
        padding: 1rem;
    }
    .hi-trace-line {
        border-left: 2px solid rgba(110, 168, 254, 0.42);
        padding: 0.15rem 0 0.15rem 0.8rem;
        color: var(--hi-soft);
        margin: 0.35rem 0;
    }
    .hi-result-callout {
        background: rgba(127, 29, 29, 0.88);
        border: 1px solid rgba(248, 113, 113, 0.8);
        border-radius: 8px;
        color: #fee2e2;
        font-weight: 750;
        padding: 1rem 1.1rem;
        margin: 1rem 0;
        text-align: center;
    }
    .hi-failure-callout {
        background: rgba(127, 29, 29, 0.35);
        border: 1px solid rgba(248, 113, 113, 0.55);
        border-radius: 8px;
        color: #fecaca;
        padding: 1rem 1.1rem;
        margin: 1rem 0;
    }
    .stButton > button {
        border-radius: 8px;
        border: 1px solid var(--hi-border);
        font-weight: 650;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb, #0891b2);
        border: 0;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="hi-page-kicker">Hackathon Intelligence</div>', unsafe_allow_html=True)
st.title("Build better hackathon ideas")
st.markdown(
    '<div class="hi-page-caption">Upload or paste the brief, choose the tracks that matter, and generate ranked ideas with evidence and developer-grade telemetry.</div>',
    unsafe_allow_html=True,
)


TRACK_KEYWORDS = {
    "Artificial Intelligence / Machine Learning": ["ai", "artificial intelligence", "machine learning", "ml", "llm", "genai", "agent"],
    "Healthcare & Life Sciences": ["health", "healthcare", "medical", "patient", "clinical", "biotech", "life sciences"],
    "Climate & Sustainability": ["climate", "sustainability", "energy", "carbon", "environment", "green"],
    "Fintech & Commerce": ["fintech", "finance", "payments", "banking", "commerce", "marketplace"],
    "Education & Workforce": ["education", "learning", "student", "teacher", "workforce", "training"],
    "Public Sector & Civic Tech": ["civic", "public sector", "government", "policy", "community", "city"],
    "Cybersecurity & Trust": ["security", "cyber", "privacy", "trust", "fraud", "identity"],
    "Developer Tools & Infrastructure": ["developer", "devtools", "infrastructure", "api", "cloud", "platform"],
    "Accessibility & Inclusion": ["accessibility", "inclusive", "disability", "assistive", "equity"],
}

MODEL_OPTIONS = [
    GEMINI_MODEL,
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]
MODEL_OPTIONS = list(dict.fromkeys(model for model in MODEL_OPTIONS if model))


def summarize_brief(text: str, max_chars: int = 340) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0] + "..."


def infer_tracks_from_text(text: str) -> list[str]:
    text_lower = (text or "").lower()
    found: list[str] = []
    for track, keywords in TRACK_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            found.append(track)

    track_lines = [
        re.sub(r"^[\s\-*#\d.)]+", "", line).strip()
        for line in (text or "").splitlines()
        if re.search(r"\b(track|theme|challenge|category)\b", line, flags=re.IGNORECASE)
    ]
    for line in track_lines[:6]:
        if 5 <= len(line) <= 90 and line not in found:
            found.append(line)

    defaults = [
        "Artificial Intelligence / Machine Learning",
        "Healthcare & Life Sciences",
        "Climate & Sustainability",
        "Education & Workforce",
        "Developer Tools & Infrastructure",
    ]
    return (found or defaults)[:8]


def reset_analysis_state() -> None:
    for key in ["analyzed_spec", "input_source_info", "detected_tracks", "selected_tracks", "run_error"]:
        st.session_state.pop(key, None)


def build_hackathon_spec(url_input: str, pdf_file: Any, pasted_text: str) -> tuple[str, str]:
    primary_spec = ""
    input_source_info = ""

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
    elif pasted_text and pasted_text.strip():
        primary_spec = pasted_text.strip()
        input_source_info = "Using pasted description as hackathon specification source."

    return primary_spec, input_source_info

# ---------------------------------------------------------
# Sidebar: API Key & Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.subheader("Access")
    st.markdown("[Get a Gemini API key](https://aistudio.google.com/apikey)", unsafe_allow_html=True)
    
    user_api_key = st.text_input(
        "Gemini API key",
        type="password",
        placeholder="Paste your Gemini API key",
    )

    env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if user_api_key and user_api_key.strip():
        st.success("Using your Gemini API key")
        effective_key = user_api_key.strip()
    elif env_key and env_key.strip():
        st.success("Using configured Gemini API key")
        effective_key = env_key.strip()
    else:
        st.warning("Add a Gemini API key to continue")
        effective_key = None

    st.divider()
    st.subheader("Run Configuration")
    selected_model = st.selectbox(
        "Model",
        options=MODEL_OPTIONS,
        index=0,
        help="If one model is under high demand, choose another and rerun.",
    )
    st.caption("Research: Tavily web search")
    st.caption("Cache: SQLite bounded cache")
    st.caption("Ranking: deterministic weighted scoring")
    st.divider()
    if st.button("Clear session state", use_container_width=True):
        for key in ["result", "trace", "run_id", "run_error", "analyzed_spec", "input_source_info", "detected_tracks", "selected_tracks"]:
            st.session_state.pop(key, None)
        st.rerun()

# ---------------------------------------------------------
# Tabs
# ---------------------------------------------------------
tab_run, tab_results, tab_metrics, tab_logs = st.tabs(["Run Agent", "Results & Ideas", "Metrics", "Run Logs"])

with tab_run:
    st.markdown('<div class="hi-panel"><span class="hi-step">1</span><strong>Brief</strong><br><span class="hi-muted">Add the hackathon source material. A URL is treated as the primary source when present.</span></div>', unsafe_allow_html=True)

    url_input = st.text_input(
        "Hackathon URL",
        placeholder="https://example.com/hackathon",
        help="Paste a hackathon webpage link."
    )

    brief_col1, brief_col2 = st.columns([1, 1])
    with brief_col1:
        pdf_file = st.file_uploader(
            "Upload hackathon PDF",
            type=["pdf"],
            help="Upload a PDF specification document."
        )
    with brief_col2:
        pasted_text = st.text_area(
            "Paste hackathon description",
            value="",
            placeholder="Paste the hackathon brief or specification text...",
            height=130,
        )

    st.divider()
    col_user, col_opts = st.columns([2, 1])
    with col_user:
        user_idea = st.text_input("Optional initial idea or domain", placeholder="e.g. Radiology report summarizer")
    with col_opts:
        additional_context = st.text_input("Optional constraints", placeholder="e.g. Privacy-compliant workflows")
        num_ideas = st.slider("Requested ideas", min_value=1, max_value=10, value=5)

    can_run = effective_key is not None
    if not can_run:
        st.info("Please enter a valid Gemini API key in the sidebar to generate ideas.")

    analyze_col, clear_col = st.columns([1, 1])
    with analyze_col:
        analyze_clicked = st.button("Analyze brief", type="primary", disabled=not can_run, use_container_width=True)
    with clear_col:
        if st.button("Reset analysis", use_container_width=True):
            reset_analysis_state()
            st.rerun()

    if analyze_clicked:
        primary_spec, input_source_info = build_hackathon_spec(url_input, pdf_file, pasted_text)
        if not primary_spec or len(primary_spec.strip()) < 10:
            st.error("Please provide a hackathon URL, upload a PDF, or paste a description (min 10 characters).")
        else:
            detected_tracks = infer_tracks_from_text(primary_spec)
            st.session_state["analyzed_spec"] = primary_spec
            st.session_state["input_source_info"] = input_source_info
            st.session_state["detected_tracks"] = detected_tracks
            st.session_state["selected_tracks"] = detected_tracks[: min(3, len(detected_tracks))]
            st.session_state.pop("result", None)
            st.session_state.pop("trace", None)
            st.session_state.pop("run_error", None)

    analyzed_spec = st.session_state.get("analyzed_spec")
    detected_tracks = st.session_state.get("detected_tracks", [])

    if analyzed_spec:
        st.markdown('<div class="hi-panel"><span class="hi-step">2</span><strong>Tracks</strong><br><span class="hi-muted">Choose one or more tracks to prioritize. The selected tracks are included in the generation prompt.</span></div>', unsafe_allow_html=True)
        if st.session_state.get("input_source_info"):
            st.info(st.session_state["input_source_info"])

        profile_col, track_col = st.columns([1.15, 1])
        with profile_col:
            st.subheader("Understanding")
            st.write(summarize_brief(analyzed_spec))
            st.caption(f"Analyzed brief length: {len(analyzed_spec):,} characters")
        with track_col:
            st.subheader("Preferred Tracks")
            prior_selected = st.session_state.get("selected_tracks", detected_tracks[: min(3, len(detected_tracks))])
            track_options = list(dict.fromkeys([*detected_tracks, *prior_selected]))
            selected_tracks = st.multiselect(
                "Choose the tracks the agent should prioritize",
                options=track_options,
                default=[track for track in prior_selected if track in track_options],
                placeholder="Select one or more tracks",
            )
            custom_track = st.text_input("Add another track", placeholder="e.g. Responsible AI for education")
            if custom_track and custom_track.strip() and custom_track.strip() not in selected_tracks:
                selected_tracks.append(custom_track.strip())
            st.session_state["selected_tracks"] = selected_tracks

        generate_disabled = not can_run or not st.session_state.get("selected_tracks")
        if generate_disabled and can_run:
            st.warning("Select at least one preferred track before generating ideas.")

        if st.button("Generate ideas", type="primary", disabled=generate_disabled, use_container_width=True):
            st.session_state.pop("result", None)
            st.session_state.pop("trace", None)
            st.session_state.pop("run_error", None)
            selected_tracks = st.session_state.get("selected_tracks", [])
            context_parts = []
            if additional_context and additional_context.strip():
                context_parts.append(additional_context.strip())
            if selected_tracks:
                context_parts.append("Preferred hackathon tracks to prioritize: " + ", ".join(selected_tracks))

            req = HackathonRequest(
                hackathon_text=analyzed_spec,
                user_idea=user_idea.strip() if user_idea else None,
                additional_context="\n".join(context_parts) if context_parts else None,
                num_ideas=num_ideas,
            )
            session_id = str(uuid.uuid4())
            st.session_state["run_id"] = session_id

            st.markdown("---")
            st.subheader("Run Progress")
            trace_placeholder = st.empty()

            live_events: list[RunTraceEvent] = []

            async def consume_live_stream():
                try:
                    async for event, final_set, run_trace in stream_hackathon_agent(
                        req,
                        session_id=session_id,
                        api_key=user_api_key.strip() if user_api_key else None,
                        model_name=selected_model,
                    ):
                        live_events.append(event)
                        
                        with trace_placeholder.container():
                            for ev in live_events:
                                if ev.type == "stage":
                                    dur_str = f"({ev.duration_ms / 1000.0:.2f}s)" if ev.duration_ms > 0 else ""
                                    st.markdown(f'<div class="hi-trace-line"><strong>{ev.stage}</strong> <span class="hi-muted">{dur_str}</span></div>', unsafe_allow_html=True)
                                elif ev.type == "llm_call":
                                    st.markdown(f'<div class="hi-trace-line"><strong>{ev.model}</strong> {ev.message} <span class="hi-muted">Input {ev.input_tokens:,} | Output {ev.output_tokens:,} | Total {ev.total_tokens:,} | {ev.duration_ms / 1000.0:.2f}s</span></div>', unsafe_allow_html=True)
                                elif ev.type == "tool_call":
                                    st.markdown(f'<div class="hi-trace-line"><strong>{ev.tool_name}</strong> <span class="hi-muted">Cache {ev.cache_status} | Results {ev.result_count} | {ev.duration_ms / 1000.0:.2f}s</span><br><span class="hi-muted">{ev.args.get("query", "")}</span></div>', unsafe_allow_html=True)
                                elif ev.type == "cache_hit":
                                    st.success(ev.message)
                                elif ev.type == "error":
                                    st.error(ev.error)

                        if final_set is not None:
                            st.session_state["result"] = final_set
                        if run_trace is not None:
                            st.session_state["trace"] = run_trace

                except Exception as exc:
                    err_text = str(exc)
                    st.session_state["run_error"] = err_text
                    if "503" in err_text or "UNAVAILABLE" in err_text or "high demand" in err_text.lower():
                        st.markdown(
                            '<div class="hi-failure-callout"><strong>Generation paused because the selected Gemini model is under high demand.</strong><br>Choose another model in the sidebar, then click Generate ideas again. Research completed, but the model did not return final ideas.</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div class="hi-failure-callout"><strong>Execution failed.</strong><br>{err_text}</div>',
                            unsafe_allow_html=True,
                        )

            asyncio.run(consume_live_stream())

            if "result" in st.session_state and "trace" in st.session_state:
                st.markdown(
                    '<div class="hi-result-callout">Run complete. See Results & Ideas.</div>',
                    unsafe_allow_html=True,
                )

    if st.session_state.get("run_error") and "result" not in st.session_state:
        st.markdown(
            '<div class="hi-failure-callout"><strong>No ideas were generated for the last run.</strong><br>Try a different model from the sidebar and rerun generation.</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------
# Display Results & Engineering Observability Panel
# ---------------------------------------------------------
if "trace" in st.session_state and "result" in st.session_state:
    tr: RunTrace = st.session_state["trace"]
    res = st.session_state["result"]

    with tab_run:
        st.markdown("---")
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Status", tr.status)
        m_col2.metric("Duration", f"{tr.duration_ms / 1000.0:.2f}s")
        m_col3.metric("Ideas Returned", f"{len(res.ideas)} / {tr.requested_ideas}")
        m_col4.metric("Tool Calls", tr.tool_calls_count)
        m_col5.metric("Total Tokens", f"{tr.token_usage.total_tokens:,}")

        with st.expander("🔬 AI engineering trace (Detailed Breakdown)", expanded=False):

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

            st.markdown("### 5. Agent Execution Timeline")
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

            st.markdown("### 7. Deterministic Ranking Trace")
            st.info(f"ℹ️ **Weight Mode:** {tr.ranking_metrics.weights_type}")
            st.write("**Weights used:**", tr.ranking_metrics.weights)

            for idx, item in enumerate(tr.ranking_metrics.ideas_scores, 1):
                st.write(
                    f"**#{idx} {item['title']}** — Final Weighted Score: **{item['final_score']:.2f} / 10**\n"
                    f"*(Fit: {item['hackathon_fit_score']} | Impact: {item['impact_score']} | Novelty: {item['novelty_score']} | Feasibility: {item['feasibility_score']} | Demo: {item['demoability_score']} | Research: {item['research_potential_score']})*"
                )

            st.divider()

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
        st.subheader(res.hackathon_profile.name or "Hackathon Profile")
        profile_cols = st.columns(4)
        profile_cols[0].metric("Theme", res.hackathon_profile.theme or "General")
        profile_cols[1].metric("Ideas", len(res.ideas))
        profile_cols[2].metric("Sources", len(res.sources))
        profile_cols[3].metric("Novelty", res.hackathon_profile.expected_novelty or "High")

        with st.expander("Hackathon requirements", expanded=False):
            req_col1, req_col2 = st.columns(2)
            with req_col1:
                st.write("Problem statements")
                st.write(res.hackathon_profile.problem_statements or ["Not specified"])
                st.write("Judging criteria")
                st.write(res.hackathon_profile.judging_criteria or ["Not specified"])
            with req_col2:
                st.write("Required technologies")
                st.write(res.hackathon_profile.required_technologies or ["Not specified"])
                st.write("Constraints")
                st.write(res.hackathon_profile.important_constraints or res.hackathon_profile.restrictions or ["Not specified"])

        st.subheader("Ranked Ideas")
        for idx, idea in enumerate(res.ideas, 1):
            score = idea.score if idea.score is not None else 0
            with st.container(border=True):
                title_col, score_col = st.columns([4, 1])
                with title_col:
                    st.markdown(f"### {idx}. {idea.title}")
                    st.write(idea.one_line_summary)
                    st.caption(f"Target user: {idea.target_user}")
                with score_col:
                    st.metric("Score", f"{score:.1f}/10")

                detail_col1, detail_col2 = st.columns(2)
                with detail_col1:
                    st.write("Problem")
                    st.write(idea.problem)
                    st.write("Solution")
                    st.write(idea.proposed_solution)
                with detail_col2:
                    st.write("Market gap")
                    st.write(idea.market_gap)
                    st.write("Technical novelty")
                    st.write(idea.technical_novelty)

                with st.expander("Scoring and risks", expanded=False):
                    st.write(
                        f"Fit {idea.hackathon_fit_score} | Impact {idea.impact_score} | "
                        f"Novelty {idea.novelty_score} | Feasibility {idea.feasibility_score} | "
                        f"Demo {idea.demoability_score} | Research {idea.research_potential_score}"
                    )
                    if idea.risks:
                        st.write("Risks")
                        st.write(idea.risks)

        with st.expander("Sources and evidence", expanded=False):
            for s in res.sources:
                st.markdown(f"- **[{s.title}]({s.url})** (`{s.domain}`)\n  {s.evidence}")

    with tab_metrics:
        st.subheader("Developer Telemetry")
        st.json(tr.model_dump())

with tab_logs:
    log_file = PROJECT_ROOT / "logs" / "run_logs.jsonl"
    if log_file.exists():
        st.code(log_file.read_text(encoding="utf-8")[-3000:])
    else:
        st.info("No logs created yet.")
