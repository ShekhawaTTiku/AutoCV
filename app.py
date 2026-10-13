"""AutoCV Streamlit Application Entrypoint.

Run with: streamlit run app.py
"""
import streamlit as st

from src.latex_parser import sections
from src.project_io import read_project, select_main, source_fingerprint
from src.ui import (
    download_buttons,
    initialize,
    open_project,
    preview,
    processing_status,
    reset,
    settings,
    start_job,
)

st.set_page_config(page_title="AutoCV · Streamlit", page_icon="📄", layout="wide")

try:
    cfg = settings()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

initialize(cfg)

busy = st.session_state.job is not None
with st.sidebar:
    st.header("AutoCV")
    for name, present in (("Gemini analysis", cfg.gemini_api_key),
                          ("Groq editing", cfg.api_key), ("Mistral repair", cfg.mistral_api_key)):
        st.write(name + ": " + ("key configured" if present else "key missing"))
    st.write("LaTeX compiler: " + ("available" if cfg.compiler else "missing"))
    st.caption("Add keys in .env, or Streamlit Secrets when hosting.")
    st.button("Refresh settings", width="stretch", disabled=busy)
    calls, tokens, estimated = st.session_state.usage.snapshot()
    st.metric("AI calls this session", f"{calls} / {cfg.request_limit}")
    st.metric("Tokens" + (" (estimated)" if estimated else ""), f"{tokens:,} / {cfg.token_limit:,}")
    st.caption("Edits send relevant content to Gemini and Groq. Compilation repairs may also send project context to Mistral.")

st.title("Edit your LaTeX resume")
st.caption("Gemini finds the section · Groq edits it · Mistral handles requested repairs.")
processing_status()

if st.session_state.project is None:
    upload = st.file_uploader(
        "Upload a .tex file or a ZIP project",
        type=["tex", "zip"],
        max_upload_size=cfg.upload_mb,
        key=f"upload_{st.session_state.uploader_generation}",
    )
    if upload is not None:
        try:
            open_project(read_project(upload.name, upload.getvalue()), cfg)
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    st.info("Upload your resume to begin. Every candidate needs your approval.")
    st.stop()

project = st.session_state.project
if not project.main_file:
    st.info("Choose the main file before compiling or editing this ZIP project.")
    main_file = st.selectbox(
        "Main .tex file",
        [""] + project.tex_files,
        format_func=lambda value: value or "Choose a file…",
    )
    if st.button("Open resume", disabled=not main_file or busy):
        open_project(select_main(project, main_file), cfg)
        st.rerun()
    st.stop()

approved = st.session_state.history[st.session_state.current]
project = approved["project"]
if st.session_state.candidate and st.session_state.candidate.get("base_id") != approved["id"]:
    st.session_state.candidate = None
baseline = st.session_state.repair_baseline
if baseline and baseline.get("base_id") != approved["id"]:
    st.session_state.repair_baseline = None

pending = st.session_state.candidate is not None
st.caption(f"{project.name} · main file: {project.main_file}")
editor, document = st.columns([1, 1.4], gap="large")

with editor:
    st.subheader("Describe your change")
    if st.session_state.notice:
        st.success(st.session_state.notice)
    if st.session_state.error:
        st.error(st.session_state.error)
    if pending:
        st.info("Approve or reject this candidate before starting another edit.")

    available = sections(project)
    if not available:
        st.warning("This template has no safely recognized section boundaries.")

    enough_budget = (calls < cfg.request_limit and tokens < cfg.token_limit)
    can_edit = bool(cfg.gemini_api_key and cfg.api_key and cfg.compiler and available and enough_budget)

    with st.form("edit_form"):
        selected = st.selectbox(
            "Target section (optional)", [""] + [s.id for s in available],
            format_func=lambda sid: "Let Gemini identify the section" if not sid else
                next(f"{s.title} · {s.file}" for s in available if s.id == sid),
            disabled=pending or busy,
        )
        instruction = st.text_area(
            "What would you like to change?",
            key="instruction",
            height=140,
            max_chars=8000,
            disabled=pending or busy,
        )
        answer = ""
        if st.session_state.question:
            st.info(st.session_state.question)
            answer = st.text_input("Your clarification", key="clarification", disabled=busy)
        applied = st.form_submit_button(
            "Apply changes",
            type="primary",
            width="stretch",
            disabled=pending or busy or not can_edit,
        )

    if applied:
        if not instruction.strip() or (st.session_state.question and not answer.strip()):
            st.session_state.error = "Enter an instruction and answer any clarification question first."
        else:
            full_instruction = instruction.strip() + ("\n\nClarification: " + answer.strip() if answer.strip() else "")
            start_job("edit", approved, cfg, full_instruction, selected or None)
        st.rerun()

    if st.session_state.proposals and not pending and not busy:
        st.caption("This request affects several sections. Run one edit at a time.")
        for index, proposal in enumerate(st.session_state.proposals):
            title = next((s.title for s in available if s.id == proposal["section_id"]), "Section")
            if st.button(f"Edit {title}: {proposal['instruction']}", key="proposal_" + str(index),
                         disabled=not can_edit):
                start_job("edit", approved, cfg, proposal["instruction"], proposal["section_id"])
                st.rerun()

    baseline = st.session_state.repair_baseline
    if baseline and not pending:
        if st.button("Try fix with Mistral", type="primary", width="stretch",
                     disabled=busy or not cfg.compiler or not cfg.mistral_api_key or not enough_budget):
            start_job("repair", approved, cfg, "Compilation repair", baseline=baseline)
            st.rerun()
        if not cfg.mistral_api_key:
            st.caption("Add MISTRAL_API_KEY to enable the repair button.")

    if st.session_state.log:
        with st.expander("Compilation details"):
            st.code(st.session_state.log, language="text")

    if not approved["pdf"] and st.button("Retry approved PDF compilation",
                                        disabled=not cfg.compiler or pending or busy):
        start_job("initial", approved, cfg)
        st.rerun()

    st.subheader("Approved versions")
    history = st.session_state.history
    version = st.selectbox(
        "Version history",
        range(len(history)),
        index=st.session_state.current,
        format_func=lambda i: f"{i + 1}. {history[i]['label']}",
        disabled=pending or busy,
    )
    if st.button("Restore selected version", disabled=pending or busy or version == st.session_state.current):
        st.session_state.current = version
        st.session_state.project = history[version]["project"]
        st.session_state.repair_baseline = None
        st.session_state.question = ""
        st.session_state.proposals = []
        st.session_state.error = ""
        st.session_state.log = ""
        st.session_state.notice = "Earlier approved source restored. Other versions remain available."
        st.rerun()

    with st.expander("Download approved files", expanded=not pending):
        download_buttons(approved, "Current approved source", "approved")

    with st.expander("End this session"):
        st.write("Download your files before clearing the temporary session.")
        if st.button("Clear session", disabled=busy):
            reset()
            st.rerun()

with document:
    candidate = st.session_state.candidate
    st.subheader("Unapproved candidate" if candidate else "Approved PDF")
    if candidate:
        valid = (candidate.get("status") == "ready" and candidate.get("pdf")
                 and candidate["pdf"].startswith(b"%PDF-") and candidate.get("base_id") == approved["id"]
                 and candidate.get("fingerprint") == source_fingerprint(candidate["project"]))
        approve, reject = st.columns(2)
        if approve.button("Approve candidate", type="primary", width="stretch", disabled=busy or not valid):
            st.session_state.history.append(candidate)
            st.session_state.current = len(st.session_state.history) - 1
            st.session_state.project = candidate["project"]
            st.session_state.candidate = None
            st.session_state.notice = "Candidate approved. Continue editing this version."
            st.session_state.clear_editor = True
            st.rerun()
        if reject.button("Reject candidate", width="stretch", disabled=busy):
            st.session_state.candidate = None
            st.session_state.notice = "Candidate rejected. Revise your instruction or start another edit."
            st.rerun()
        download_buttons(candidate, "UNAPPROVED downloads do not approve this candidate.", "candidate")
    preview(candidate or approved)
