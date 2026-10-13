"""AutoCV Streamlit Application Entrypoint.

Run with: streamlit run app.py
"""
import streamlit as st

from src.latex_parser import sections
from src.project_io import read_project, select_main, source_fingerprint
from src.ui import (
    candidate_badge,
    divider_label,
    download_buttons,
    file_chip,
    inject_theme,
    initialize,
    open_project,
    page_header,
    preview,
    processing_status,
    reset,
    section_label,
    settings,
    sidebar_brand,
    start_job,
    status_row,
)

st.set_page_config(
    page_title="AutoCV · AI LaTeX Resume Studio",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom design tokens and dark aesthetic
inject_theme()

# ── Configuration & State Initialization ─────────────────────────────────────
try:
    cfg = settings()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

initialize(cfg)

busy = st.session_state.job is not None
calls, tokens, estimated = st.session_state.usage.snapshot()

# ── Sidebar Console ──────────────────────────────────────────────────────────
with st.sidebar:
    sidebar_brand()

    section_label("Engine Pipeline")
    status_row("Gemini Analysis", bool(cfg.gemini_api_key))
    status_row("Groq Fast-Editor", bool(cfg.api_key))
    status_row("Mistral Auto-Repair", bool(cfg.mistral_api_key))
    status_row("LaTeX Compiler", bool(cfg.compiler), ok_text="Active", bad_text="Not Found")

    st.caption("Keys configure automatically via `.env` or Streamlit Cloud Secrets.")
    st.button("↺  Refresh Config", use_container_width=True, disabled=busy)

    divider_label("Session Metrics")
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("AI Calls", f"{calls} / {cfg.request_limit}")
    m_col2.metric(
        "Tokens" + (" ~est" if estimated else ""),
        f"{tokens // 1000}k / {cfg.token_limit // 1000}k",
    )

    st.caption("Scoped updates only stream modified LaTeX sections to preserve token budget.")

# ── State 1: Landing Page (No Project Loaded) ────────────────────────────────
if st.session_state.project is None:
    page_header(
        "AI-Powered LaTeX Resume Engineering",
        "Targeted edits with precision compilation — no prompt gymnastics, no destroyed formatting.",
    )

    processing_status()

    # Upload Container Card
    st.markdown(
        """
        <div style="max-width: 680px; margin: 0 auto; padding: 0.5rem 0 1.5rem 0;">
        """,
        unsafe_allow_html=True,
    )

    upload = st.file_uploader(
        "Upload your resume (.tex source or .zip bundle)",
        type=["tex", "zip"],
        max_upload_size=cfg.upload_mb,
        key=f"upload_{st.session_state.uploader_generation}",
        label_visibility="visible",
    )

    if upload is not None:
        try:
            open_project(read_project(upload.name, upload.getvalue()), cfg)
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)

    # 3-Card Architecture Overview
    divider_label("How AutoCV Works")
    feat_gemini, feat_groq, feat_mistral = st.columns(3)

    with feat_gemini:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon-wrapper" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa;">🎯</div>
                <div style="font-weight: 700; font-size: 0.98rem; margin-bottom: 0.35rem; color: #f8fafc;">1. Gemini Isolation</div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.45;">
                    Parses your TeX AST and isolates the exact target section, preventing unintended structural changes.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with feat_groq:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon-wrapper" style="background: rgba(99, 102, 241, 0.15); color: #818cf8;">⚡</div>
                <div style="font-weight: 700; font-size: 0.98rem; margin-bottom: 0.35rem; color: #f8fafc;">2. Groq Generation</div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.45;">
                    Executes your content edits with ultra-low latency while preserving LaTeX syntax commands and styling.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with feat_mistral:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon-wrapper" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">🛠️</div>
                <div style="font-weight: 700; font-size: 0.98rem; margin-bottom: 0.35rem; color: #f8fafc;">3. Mistral Compiler Fix</div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.45;">
                    Self-healing loop: catches pdflatex / tectonic syntax breaks and patches errors automatically.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.stop()

# ── State 2: Main File Selection (Multi-file Zip) ────────────────────────────
project = st.session_state.project
if not project.main_file:
    page_header("Select Primary Source", "Choose the root .tex file to compile for this project.")
    main_file = st.selectbox(
        "Main .tex file",
        [""] + project.tex_files,
        format_func=lambda v: "Select a document…" if not v else v,
    )
    if st.button("Open Resume Workspace →", type="primary", disabled=not main_file or busy):
        open_project(select_main(project, main_file), cfg)
        st.rerun()
    st.stop()

# ── State 3: Active Studio Workspace ─────────────────────────────────────────
approved = st.session_state.history[st.session_state.current]
project = approved["project"]

# Protect against mismatched candidate bases
if st.session_state.candidate and st.session_state.candidate.get("base_id") != approved["id"]:
    st.session_state.candidate = None
baseline = st.session_state.repair_baseline
if baseline and baseline.get("base_id") != approved["id"]:
    st.session_state.repair_baseline = None

pending = st.session_state.candidate is not None

# Workspace Header
hdr_col, info_col = st.columns([3, 1.2])
with hdr_col:
    page_header(
        "Resume Studio",
        "Review AI-generated changes side-by-side with your compiled PDF.",
    )
with info_col:
    st.markdown("<div style='padding-top: 1.8rem;'></div>", unsafe_allow_html=True)
    file_chip(f"{project.name} · {project.main_file}")

processing_status()

# Studio 2-Column Split
editor_col, doc_col = st.columns([1, 1.45], gap="large")

# ──────────────────────── LEFT COLUMN: Instruction Console ───────────────────
with editor_col:
    if st.session_state.notice:
        st.success(st.session_state.notice)
    if st.session_state.error:
        st.error(st.session_state.error)
    if pending:
        st.info("⚡ An AI edit candidate is awaiting your review. Approve or reject it to proceed.")

    available = sections(project)
    if not available:
        st.warning("⚠ No section headers found in template. Edits will operate on the full document.")

    enough_budget = calls < cfg.request_limit and tokens < cfg.token_limit
    has_any_provider = bool(cfg.gemini_api_key or cfg.mistral_api_key or cfg.api_key)
    can_edit = bool(has_any_provider and cfg.compiler and available and enough_budget)

    # Edit Form
    section_label("Draft Your Change")
    with st.form("edit_form"):
        selected = st.selectbox(
            "Target section (optional)",
            [""] + [s.id for s in available],
            format_func=lambda sid: "✦  Auto-detect target section with Gemini"
            if not sid
            else next(f"{s.title}  ·  {s.file}" for s in available if s.id == sid),
            disabled=pending or busy,
        )
        instruction = st.text_area(
            "Instruction",
            key="instruction",
            height=130,
            max_chars=8000,
            placeholder="e.g. Expand on my technical leadership in the Experience section with metrics on team growth and latency reduction…",
            disabled=pending or busy,
            label_visibility="collapsed",
        )
        answer = ""
        if st.session_state.question:
            st.info(f"💬 Clarification needed: {st.session_state.question}")
            answer = st.text_input("Your Response", key="clarification", disabled=busy)

        applied = st.form_submit_button(
            "Apply changes",
            type="primary",
            use_container_width=True,
            disabled=pending or busy or not can_edit,
        )

    if applied:
        if not instruction.strip() or (st.session_state.question and not answer.strip()):
            st.session_state.error = "Please provide your instructions and answer any clarifying question."
        else:
            full_instruction = instruction.strip() + (
                "\n\nClarification: " + answer.strip() if answer.strip() else ""
            )
            start_job("edit", approved, cfg, full_instruction, selected or None)
        st.rerun()

    # Multi-section Proposals
    if st.session_state.proposals and not pending and not busy:
        divider_label("Section Edit Proposals")
        st.caption("This change spans multiple sections. Run one targeted edit at a time:")
        for idx, prop in enumerate(st.session_state.proposals):
            p_title = next((s.title for s in available if s.id == prop["section_id"]), "Section")
            if st.button(
                f"✎  {p_title}: {prop['instruction']}",
                key=f"prop_{idx}",
                use_container_width=True,
                disabled=not can_edit,
            ):
                start_job("edit", approved, cfg, prop["instruction"], prop["section_id"])
                st.rerun()

    # Mistral Auto-Repair Button
    baseline = st.session_state.repair_baseline
    if baseline and not pending:
        divider_label("Compilation Diagnostic")
        if st.button(
            "Try fix with Mistral",
            type="primary",
            use_container_width=True,
            disabled=busy or not cfg.compiler or not cfg.mistral_api_key or not enough_budget,
        ):
            start_job("repair", approved, cfg, "Compilation repair", baseline=baseline)
            st.rerun()
        if not cfg.mistral_api_key:
            st.caption("Add `MISTRAL_API_KEY` to enable autonomous compiler fixes.")

    # Compilation Log
    if st.session_state.log:
        with st.expander("📋  Compiler Diagnostics Log", expanded=False):
            st.code(st.session_state.log, language="text")

    if not approved["pdf"] and st.button(
        "⟳  Recompile Approved Version",
        disabled=not cfg.compiler or pending or busy,
        use_container_width=True,
    ):
        start_job("initial", approved, cfg)
        st.rerun()

    # Version History Dropdown
    divider_label("Revision History")
    history = st.session_state.history
    version = st.selectbox(
        "Revisions",
        range(len(history)),
        index=st.session_state.current,
        format_func=lambda i: f"v{i + 1}  ·  {history[i]['label']}",
        disabled=pending or busy,
        label_visibility="collapsed",
    )
    if st.button(
        "Rollback to Selected Revision",
        use_container_width=True,
        disabled=pending or busy or version == st.session_state.current,
    ):
        st.session_state.current = version
        st.session_state.project = history[version]["project"]
        st.session_state.repair_baseline = None
        st.session_state.question = ""
        st.session_state.proposals = []
        st.session_state.error = ""
        st.session_state.log = ""
        st.session_state.notice = f"Rolled back to v{version + 1}."
        st.rerun()

    # Downloads & Session Reset
    with st.expander("⬇  Export Approved Files", expanded=not pending):
        download_buttons(approved, "Active approved files", "approved")

    with st.expander("⚠  Session Reset"):
        st.markdown(
            "<p style='color: #94a3b8; font-size: 0.82rem;'>Make sure to export your files before closing the session.</p>",
            unsafe_allow_html=True,
        )
        if st.button("Clear Session & Reset", disabled=busy, use_container_width=True):
            reset()
            st.rerun()

# ──────────────────────── RIGHT COLUMN: Live Document Preview ─────────────────
with doc_col:
    candidate = st.session_state.candidate

    candidate_badge(candidate is not None)

    if candidate:
        valid = (
            candidate.get("status") == "ready"
            and candidate.get("pdf")
            and candidate["pdf"].startswith(b"%PDF-")
            and candidate.get("base_id") == approved["id"]
            and candidate.get("fingerprint") == source_fingerprint(candidate["project"])
        )
        col_approve, col_reject = st.columns(2)
        with col_approve:
            if st.button(
                "Approve candidate",
                type="primary",
                use_container_width=True,
                disabled=busy or not valid,
            ):
                st.session_state.history.append(candidate)
                st.session_state.current = len(st.session_state.history) - 1
                st.session_state.project = candidate["project"]
                st.session_state.candidate = None
                st.session_state.notice = "Candidate approved and committed to history."
                st.session_state.clear_editor = True
                st.rerun()

        with col_reject:
            if st.button("Reject candidate", use_container_width=True, disabled=busy):
                st.session_state.candidate = None
                st.session_state.notice = "Candidate discarded. Approved version unchanged."
                st.rerun()

        with st.expander("⬇  Inspect Candidate Source (Unapproved)", expanded=False):
            download_buttons(
                candidate,
                "Candidate files reflect the proposed AI change prior to approval.",
                "candidate",
            )

    preview(candidate or approved)
