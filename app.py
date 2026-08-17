"""Person D: Streamlit voice + UI for the product-discovery LangGraph."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from voice_utils import synthesize_speech, transcribe_audio

load_dotenv()

st.set_page_config(
    page_title="Voice Product Discovery",
    page_icon="🎙️",
    layout="wide",
)


def run_graph_isolated(transcript: str) -> dict:
    """
    Run Person C's LangGraph + MCP stack in a short-lived child Python process.

    On this Mac, the graph completes successfully but the Python process can
    segfault during async/native cleanup afterward. Keeping that stack out of
    Streamlit means a cleanup crash cannot take down the UI.
    """
    worker = os.path.join(os.path.dirname(__file__), "ui_pipeline_worker.py")
    proc = subprocess.run(
        [sys.executable, worker],
        input=transcript,
        text=True,
        capture_output=True,
        cwd=os.path.dirname(__file__),
        env=os.environ.copy(),
        timeout=120,
    )

    # The worker prints one machine-readable line before exiting.
    result_line = None
    for line in proc.stdout.splitlines():
        if line.startswith("__UI_RESULT__"):
            result_line = line[len("__UI_RESULT__"):]

    if result_line is None:
        detail = (proc.stderr or proc.stdout or f"worker exit code {proc.returncode}").strip()
        raise RuntimeError(
            "The LangGraph worker did not return a result. "
            f"Worker details: {detail[-3000:]}"
        )

    return json.loads(result_line)


def money(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return f"${float(str(value).replace('$', '').replace(',', '')):.2f}"
    except (TypeError, ValueError):
        return str(value)


def comparison_rows(merged_results: list[dict]) -> list[dict]:
    """Flatten Person C's merged result objects into UI-friendly table rows."""
    rows: list[dict] = []
    for item in merged_results:
        rag = item.get("rag_item") or {}
        web = item.get("web_item") or {}
        title = rag.get("title") or web.get("title") or "Untitled result"

        rows.append(
            {
                "Product": title,
                "Source match": item.get("match_type", ""),
                "Brand": rag.get("brand") or "—",
                "Catalog price": money(rag.get("price")) or "—",
                "Live price": money(web.get("price")) or "—",
                "Availability": web.get("availability") or "—",
                "Catalog citation": rag.get("doc_id") or "—",
                "Live URL": web.get("url") or "—",
                "Discrepancy": ", ".join(item.get("discrepancy_notes") or []) or "—",
            }
        )
    return rows


def render_agent_log(result: dict) -> None:
    constraints = result.get("constraints") or {}
    plan = result.get("plan") or {}

    with st.expander("Agent step log", expanded=True):
        st.markdown("**1. Router — understood constraints**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Max price", money(constraints.get("max_price")) or "None")
        c2.metric("Min price", money(constraints.get("min_price")) or "None")
        c3.metric("Brand", constraints.get("brand") or "None")
        c4.metric("Subcategory", constraints.get("subcategory") or "None")

        if constraints.get("age_mentioned"):
            st.caption("Age was mentioned, but it is intentionally not used as a retrieval filter for this dataset.")
        if constraints.get("safety_flags"):
            st.warning("Safety flags: " + ", ".join(constraints["safety_flags"]))

        st.markdown("**2. Planner — tool plan**")
        st.write(
            {
                "rag.search": bool(plan.get("call_rag")),
                "web.search": bool(plan.get("call_web")),
                "reason": plan.get("reason", ""),
            }
        )

        st.markdown("**3. Retriever — evidence**")
        st.write(f"Merged evidence rows: {len(result.get('merged_results') or [])}")

        st.markdown("**4. Critic — grounded response**")
        st.write("Generated the spoken answer, full answer, and citations shown below.")


def render_citations(citations: list[dict]) -> None:
    if not citations:
        st.info("No citations were returned for this answer.")
        return

    for idx, citation in enumerate(citations, start=1):
        doc_id = citation.get("doc_id")
        url = citation.get("url")
        claim = citation.get("claim") or "Source"
        pieces = []
        if doc_id:
            pieces.append(f"private catalog `{doc_id}`")
        if url:
            pieces.append(f"[live source]({url})")
        st.markdown(f"**{idx}. {claim}** — " + " + ".join(pieces))


def init_state() -> None:
    defaults = {
        "transcript": "",
        "result": None,
        "tts_audio": None,
        "last_audio_signature": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def run_pipeline(transcript: str) -> None:
    transcript = transcript.strip()
    if not transcript:
        st.warning("Please record or type a request first.")
        return

    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is missing from your .env file.")
        return

    try:
        with st.spinner("Running Router → Planner → Retriever → Critic..."):
            result = run_graph_isolated(transcript)
        st.session_state.result = result

        spoken = (result.get("answer") or "").strip()
        st.session_state.tts_audio = None
        if spoken:
            try:
                with st.spinner("Generating spoken response..."):
                    st.session_state.tts_audio = synthesize_speech(spoken)
            except Exception as tts_exc:
                st.warning("The recommendation worked, but spoken playback could not be generated.")
                st.exception(tts_exc)
    except Exception as exc:
        st.session_state.result = None
        st.session_state.tts_audio = None
        st.error("The assistant could not complete the request.")
        st.exception(exc)


init_state()

st.title("🎙️ Voice-to-Voice Product Discovery Assistant")
st.caption("Toys & Games · LangGraph multi-agent flow · private RAG + optional live web search")

with st.sidebar:
    st.header("Demo status")
    st.write("✅ Voice input")
    st.write("✅ Speech-to-text")
    st.write("✅ LangGraph agent flow")
    st.write("✅ Comparison table + citations")
    st.write("✅ Text-to-speech playback")
    st.divider()
    st.caption("Tip: ask for **current price** or **availability** to trigger the live web tool.")

voice_tab, text_tab = st.tabs(["🎤 Speak", "⌨️ Type"])

with voice_tab:
    audio = st.audio_input("Record your shopping request")
    if audio is not None:
        # Avoid paying for/transcribing the exact same recording on every Streamlit rerun.
        signature = (audio.name, len(audio.getvalue()), hash(audio.getvalue()))
        if signature != st.session_state.last_audio_signature:
            try:
                with st.spinner("Transcribing your recording..."):
                    transcript = transcribe_audio(audio, filename=audio.name or "recording.wav")
                st.session_state.transcript = transcript
                st.session_state.last_audio_signature = signature
            except Exception as exc:
                st.error("Speech recognition failed.")
                st.exception(exc)

    if st.session_state.transcript:
        st.markdown("**Transcript**")
        st.info(st.session_state.transcript)

    if st.button("Find products from my recording", type="primary", use_container_width=True):
        run_pipeline(st.session_state.transcript)

with text_tab:
    typed = st.text_area(
        "Type a request",
        value=st.session_state.transcript,
        placeholder="e.g., Is there a building set under $30 available right now?",
        height=110,
    )
    if st.button("Find products from text", type="primary", use_container_width=True):
        st.session_state.transcript = typed
        run_pipeline(typed)

result = st.session_state.result
if result:
    st.divider()
    st.subheader("Assistant response")

    left, right = st.columns([2, 1])
    with left:
        st.markdown(result.get("full_answer") or result.get("answer") or "No answer returned.")
    with right:
        if st.session_state.tts_audio:
            st.markdown("**Spoken answer**")
            st.audio(st.session_state.tts_audio, format="audio/mp3")
        else:
            st.caption("No audio response was generated.")

    render_agent_log(result)

    st.subheader("Product comparison")
    rows = comparison_rows(result.get("merged_results") or [])
    if rows:
        # Avoid st.dataframe/pandas/pyarrow here. On the affected Intel Mac,
        # the native Arrow serialization path can terminate Python with SIGSEGV.
        for idx, row in enumerate(rows[:10], start=1):
            with st.container(border=True):
                st.markdown(f"**{idx}. {row['Product']}**")
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Brand:** {row['Brand']}")
                c1.write(f"**Source match:** {row['Source match'] or '—'}")
                c2.write(f"**Catalog price:** {row['Catalog price']}")
                c2.write(f"**Live price:** {row['Live price']}")
                c3.write(f"**Availability:** {row['Availability']}")
                c3.write(f"**Catalog citation:** {row['Catalog citation']}")
                if row["Live URL"] not in ("—", "", None):
                    st.link_button("Open live source", row["Live URL"])
                if row["Discrepancy"] not in ("—", "", None):
                    st.caption("Discrepancy: " + row["Discrepancy"])
    else:
        st.info("No product evidence was returned.")

    st.subheader("Citations & data lineage")
    render_citations(result.get("citations") or [])
