"""Streamlit visual components, progress indicators, preview panes, and download handlers."""
from pathlib import Path
from uuid import uuid4

import pymupdf
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.config import load_settings
from src.pdf import page_count, render_page
from src.project_io import project_zip, source_bytes, source_fingerprint
from src.ui.state import finish_job, start_job


def settings():
    """Retrieve app settings from Streamlit secrets (hosted) or .env (local)."""
    try:
        secrets = st.secrets.to_dict()
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        secrets = {}
    try:
        import core
        loader = getattr(core, "load_settings", load_settings)
    except ImportError:
        loader = load_settings
    return loader(secrets)


@st.fragment(run_every=0.5)
def processing_status():
    """Real-time job progress bar, token metric reporter, and cancel button."""
    job = st.session_state.job
    if not job:
        return
    if job.done.is_set():
        finish_job(job)
        st.rerun()

    is_cancelling = job.cancelled.is_set()
    stage_text = "Cancellation requested; stopping active operation…" if is_cancelling else job.stage
    used, tokens, estimated = st.session_state.usage.snapshot()
    est_tag = " (~est)" if estimated else ""

    banner_col1, banner_col2 = st.columns([4, 1])
    with banner_col1:
        st.markdown(
            f"""
            <div class="processing-banner">
                <span class="pulse-dot"></span>
                <div>
                    <div style="font-weight: 600; font-size: 0.9rem; color: #f0f4ff;">{stage_text}</div>
                    <div style="font-size: 0.75rem; color: #8b95b0; margin-top: 2px;">
                        AI calls: {used} · Tokens: {tokens:,}{est_tag}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with banner_col2:
        st.markdown("<div style='padding-top: 6px;'></div>", unsafe_allow_html=True)
        if st.button("Cancel request", key="cancel_" + job.id, disabled=is_cancelling, use_container_width=True):
            job.cancelled.set()
            st.rerun()


def open_project(project, cfg):
    """Initialize a newly uploaded project into session state."""
    snapshot = {
        "id": uuid4().hex, "project": project, "pdf": None,
        "fingerprint": source_fingerprint(project), "label": "Original upload",
    }
    st.session_state.project = project
    st.session_state.history = [snapshot]
    st.session_state.current = 0
    st.session_state.candidate = None
    st.session_state.repair_baseline = None
    st.session_state.question = ""
    st.session_state.proposals = []
    st.session_state.error = ""
    st.session_state.log = ""
    if project.main_file and cfg.compiler:
        start_job("initial", snapshot, cfg)


def download_buttons(snapshot: dict, label: str, prefix: str):
    """Render export download buttons for .tex source, .zip bundle, and .pdf."""
    project = snapshot["project"]
    stem = Path(project.name).stem
    marker = "UNAPPROVED" if prefix == "candidate" else "approved"
    st.caption(label)
    first, second, third = st.columns(3)
    first.download_button("LaTeX source", source_bytes(project), file_name=f"{stem}-{marker}.tex",
                          mime="application/x-tex", key=prefix + "_tex", on_click="ignore", width="stretch")
    second.download_button("Complete ZIP", project_zip(project), file_name=f"{stem}-{marker}.zip",
                           mime="application/zip", key=prefix + "_zip", on_click="ignore", width="stretch")
    if snapshot.get("pdf") and snapshot.get("fingerprint") == source_fingerprint(project):
        third.download_button("PDF", snapshot["pdf"], file_name=f"{stem}-{marker}.pdf",
                              mime="application/pdf", key=prefix + "_pdf", on_click="ignore", width="stretch")


def preview(snapshot: dict):
    """Render scrollable multi-page PDF preview with quick-jump pill buttons."""
    pdf_bytes = snapshot.get("pdf")
    if not pdf_bytes:
        st.markdown(
            """
            <div class="acv-card" style="text-align: center; padding: 4rem 2rem; margin-top: 0.5rem;">
                <div style="font-size: 2.5rem; margin-bottom: 0.75rem; opacity: 0.7;">📄</div>
                <div style="font-weight: 700; font-size: 1.05rem; color: #f0f4ff; margin-bottom: 0.35rem;">PDF Preview Pending</div>
                <div style="color: #8b95b0; font-size: 0.85rem; max-width: 320px; margin: 0 auto; line-height: 1.4;">
                    Your live multi-page document preview will appear here once LaTeX compiles.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    if snapshot.get("fingerprint") != source_fingerprint(snapshot["project"]):
        st.error("This PDF no longer matches its source. Compile again before reviewing.")
        return
    try:
        count = page_count(pdf_bytes)
    except (RuntimeError, ValueError, pymupdf.FileDataError):
        st.error("The PDF could not be displayed. You can still download it.")
        return

    # Quick-jump pill buttons (only shown when document has more than one page)
    jump_to = None
    if count > 1:
        st.caption(f"{count} pages · scroll or jump to a page:")
        jump_cols = st.columns(min(count, 10))
        for i, col in enumerate(jump_cols[:count]):
            if col.button(f"{i + 1}", key=f"jump_{snapshot['id']}_{i}", use_container_width=True):
                jump_to = i

    # Scrollable container holding all pages
    scroll_height = 800
    with st.container(height=scroll_height, border=False):
        try:
            for page_index in range(count):
                if count > 1:
                    anchor_id = f"page-{page_index + 1}-{snapshot['id']}"
                    st.markdown(
                        f"<div id='{anchor_id}' style='text-align: center; color: #888; font-size: 0.85rem; padding: 6px 0;'>"
                        f"— Page {page_index + 1} of {count} —"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.image(render_page(pdf_bytes, page_index), width="stretch")
        except (RuntimeError, ValueError, pymupdf.FileDataError):
            st.error("The PDF could not be displayed. You can still download it.")
            return

    # JavaScript anchor-scroll after a quick-jump button is pressed
    if jump_to is not None:
        anchor = f"page-{jump_to + 1}-{snapshot['id']}"
        st.components.v1.html(
            f"""<script>
                try {{
                    const doc = window.parent.document || document;
                    const el = doc.getElementById('{anchor}');
                    if (el) {{
                        el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                    }}
                }} catch(e) {{
                    const el = document.getElementById('{anchor}');
                    if (el) {{
                        el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                    }}
                }}
            </script>""",
            height=0,
        )
