"""AutoCV custom CSS theme injection and UI layout helpers for Streamlit."""

import streamlit as st

AUTOCV_CSS = """
<style>
/* ── Google Fonts & Icon Symbols ─────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

/* ── Design Tokens ──────────────────────────────────────────────── */
:root {
    --bg-base:        #080a0f;
    --bg-surface:     #0e121a;
    --bg-card:        #131823;
    --bg-card-hover:  #182030;
    --bg-glass:       rgba(19, 24, 35, 0.82);
    --border:         rgba(99, 115, 155, 0.16);
    --border-hover:   rgba(99, 178, 255, 0.4);

    --accent-blue:    #3b82f6;
    --accent-indigo:  #6366f1;
    --accent-purple:  #8b5cf6;
    --accent-cyan:    #06b6d4;
    --accent-emerald: #10b981;
    --accent-amber:   #f59e0b;
    --accent-rose:    #f43f5e;

    --gradient-brand:    linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
    --gradient-primary:  linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
    --gradient-card:     linear-gradient(180deg, rgba(25, 32, 48, 0.6) 0%, rgba(14, 18, 26, 0.9) 100%);
    --gradient-glow:     radial-gradient(ellipse 80% 50% at 50% -10%, rgba(59, 130, 246, 0.15) 0%, transparent 60%);

    --text-primary:   #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;

    --radius-sm:  6px;
    --radius-md:  10px;
    --radius-lg:  16px;
    --radius-xl:  22px;

    --shadow-card: 0 4px 20px -2px rgba(0, 0, 0, 0.5), 0 0 1px 1px rgba(255, 255, 255, 0.05);
    --shadow-glow: 0 0 35px rgba(59, 130, 246, 0.18);
    --transition: 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

/* ── Typography & Global Reset ──────────────────────────────────── */
html, body {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Apply main UI font safely without overriding icon font spans */
p, label, h1, h2, h3, h4, h5, h6, input, textarea, select {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

code, kbd, samp, pre, [class*="mono"] {
    font-family: 'JetBrains Mono', monospace !important;
}

/* ── Preserve and Lock Streamlit Material Icon Fonts ───────────── */
[data-testid="stIconMaterial"],
[data-testid="stIconMaterial"] *,
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons,
[class*="material-symbols"],
[class*="material-icons"],
[class*="e1vmumty"] {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    font-size: 1.15rem !important;
    line-height: 1 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' 1 !important;
    font-feature-settings: 'liga' 1 !important;
}

/* ── Deep Space App Canvas ──────────────────────────────────────── */
.stApp {
    background-color: var(--bg-base) !important;
    background-image:
        radial-gradient(ellipse 70% 40% at 50% 0%, rgba(59, 130, 246, 0.12) 0%, transparent 70%),
        radial-gradient(ellipse 50% 40% at 100% 100%, rgba(139, 92, 246, 0.08) 0%, transparent 60%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
}

.stMain, .stMainBlockContainer {
    background: transparent !important;
}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
    max-width: 1350px !important;
}

/* ── Sidebar: Elevated Studio Console ───────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
    box-shadow: 6px 0 30px rgba(0, 0, 0, 0.45) !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem !important;
}

.sidebar-brand-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0.5rem 0.5rem 1.25rem 0.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.25rem;
}

.brand-gem {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: var(--gradient-brand);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    font-size: 1.15rem;
}

.brand-title {
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #ffffff 30%, #94a3b8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
}

.brand-badge {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--accent-cyan);
    background: rgba(6, 182, 212, 0.12);
    border: 1px solid rgba(6, 182, 212, 0.25);
    border-radius: 4px;
    padding: 1px 6px;
    margin-top: 2px;
    display: inline-block;
}

/* Status row indicators */
.status-row-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.4rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    font-size: 0.82rem;
}

.status-row-label {
    color: var(--text-secondary);
    font-weight: 500;
}

.status-badge {
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    font-family: 'JetBrains Mono', monospace;
}

.status-badge.ok {
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-badge.bad {
    background: rgba(244, 63, 94, 0.12);
    color: #fb7185;
    border: 1px solid rgba(244, 63, 94, 0.25);
}

/* ── Hero Banner ────────────────────────────────────────────────── */
.hero-box {
    margin-bottom: 1.5rem;
    padding: 1rem 0 0.5rem 0;
}

.hero-title {
    font-size: 2.25rem;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #94a3b8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    line-height: 1.15;
}

.hero-subtitle {
    color: var(--text-secondary) !important;
    font-size: 0.95rem;
    margin-top: 0.4rem;
    font-weight: 400;
}

/* ── Modern Card Containers ─────────────────────────────────────── */
.glass-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
    box-shadow: var(--shadow-card);
    transition: border-color var(--transition), box-shadow var(--transition);
}

.glass-card:hover {
    border-color: var(--border-hover);
    box-shadow: var(--shadow-card), var(--shadow-glow);
}

/* ── Step & Feature Cards (Landing) ─────────────────────────────── */
.feature-card {
    background: var(--gradient-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.4rem 1.2rem;
    text-align: center;
    transition: transform var(--transition), border-color var(--transition);
}

.feature-card:hover {
    transform: translateY(-3px);
    border-color: rgba(99, 102, 241, 0.4);
}

.feature-icon-wrapper {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    margin: 0 auto 0.9rem auto;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
}

/* ── Chips & Badges ─────────────────────────────────────────────── */
.meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 5px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--accent-cyan);
}

.candidate-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 100px;
    padding: 5px 14px;
    font-size: 0.82rem;
    font-weight: 600;
    color: #fbbf24;
    margin-bottom: 0.85rem;
}

.approved-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 100px;
    padding: 5px 14px;
    font-size: 0.82rem;
    font-weight: 600;
    color: #34d399;
    margin-bottom: 0.85rem;
}

/* ── Section Dividers & Labels ──────────────────────────────────── */
.sub-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-muted);
    margin: 0.8rem 0 0.4rem 0;
}

.divider-strip {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 1.4rem 0 1rem 0;
}

.divider-strip::before, .divider-strip::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
}

.divider-strip span {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--text-muted);
}

/* ── Inputs, Textarea, Select ───────────────────────────────────── */
.stTextArea textarea, .stTextInput input {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-size: 0.92rem !important;
    transition: all var(--transition) !important;
}

.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent-blue) !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18) !important;
    background: #111624 !important;
    outline: none !important;
}

[data-testid="stSelectbox"] > div > div {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    transition: border-color var(--transition) !important;
}

[data-testid="stSelectbox"] > div > div:hover {
    border-color: var(--border-hover) !important;
}

/* ── Buttons ────────────────────────────────────────────────────── */
.stButton > button {
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    border-radius: var(--radius-md) !important;
    padding: 0.55rem 1.15rem !important;
    transition: all var(--transition) !important;
    letter-spacing: 0.1px !important;
}

/* Primary Button (Gradient) */
.stButton > button[kind="primary"] {
    background: var(--gradient-primary) !important;
    border: none !important;
    color: #ffffff !important;
    box-shadow: 0 4px 16px rgba(59, 130, 246, 0.35) !important;
}

.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 24px rgba(99, 102, 241, 0.55) !important;
    transform: translateY(-1px) !important;
}

.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
}

/* Secondary Button */
.stButton > button:not([kind="primary"]) {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
}

.stButton > button:not([kind="primary"]):hover {
    background: var(--bg-card-hover) !important;
    border-color: var(--border-hover) !important;
    color: #ffffff !important;
}

/* Download Buttons */
.stDownloadButton > button {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    color: var(--text-primary) !important;
    transition: all var(--transition) !important;
}

.stDownloadButton > button:hover {
    background: rgba(59, 130, 246, 0.12) !important;
    border-color: var(--accent-blue) !important;
    color: var(--accent-blue) !important;
}

/* ── Metric Display ─────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    padding: 0.8rem 1rem !important;
}

[data-testid="stMetricLabel"] {
    color: var(--text-muted) !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.8px !important;
    text-transform: uppercase !important;
}

[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-weight: 800 !important;
    font-size: 1.35rem !important;
}

/* ── Expanders ──────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
}

[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    color: var(--text-secondary) !important;
    padding: 0.8rem 1rem !important;
}

[data-testid="stExpander"] summary:hover {
    color: var(--text-primary) !important;
}

/* ── Alerts ─────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
    border-left-width: 4px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
}

/* ── File Uploader Dropzone & Browse Button ──────────────────────── */
[data-testid="stFileUploader"] {
    width: 100% !important;
}

/* Dropzone container */
[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploader"] section {
    background: var(--bg-card) !important;
    border: 2px dashed rgba(99, 115, 155, 0.28) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1.75rem 1.5rem !important;
    transition: all var(--transition) !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 16px !important;
}

[data-testid="stFileUploaderDropzone"]:hover,
[data-testid="stFileUploader"] section:hover {
    border-color: var(--accent-blue) !important;
    background: rgba(59, 130, 246, 0.05) !important;
    box-shadow: 0 0 25px rgba(59, 130, 246, 0.12) !important;
}

/* File Uploader button styling */
[data-testid="stFileUploader"] button,
[data-testid="stFileUploaderDropzone"] button {
    background: rgba(30, 41, 59, 0.85) !important;
    border: 1px solid rgba(99, 115, 155, 0.35) !important;
    border-radius: var(--radius-md) !important;
    color: #f8fafc !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.5rem 1.15rem !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    white-space: nowrap !important;
    min-width: 110px !important;
    transition: all var(--transition) !important;
}

[data-testid="stFileUploader"] button:hover,
[data-testid="stFileUploaderDropzone"] button:hover {
    background: rgba(59, 130, 246, 0.2) !important;
    border-color: var(--accent-blue) !important;
    color: #60a5fa !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.25) !important;
}

/* Icon inside upload button */
[data-testid="stFileUploader"] button [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] button [data-testid="stIconMaterial"] {
    font-size: 1.15rem !important;
    margin-right: 4px !important;
}

/* Dropzone instruction label */
[data-testid="stFileUploaderDropzoneInstructions"] {
    color: var(--text-secondary) !important;
    font-size: 0.84rem !important;
    line-height: 1.4 !important;
}

/* ── Code Blocks ────────────────────────────────────────────────── */
.stCode, code, pre {
    background: #06080d !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color: #93c5fd !important;
    font-size: 0.82rem !important;
}

/* ── Progress & Processing Banner ───────────────────────────────── */
.live-status-banner {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.12) 0%, rgba(139, 92, 246, 0.12) 100%);
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: var(--radius-md);
    padding: 0.85rem 1.15rem;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: 12px;
}

@keyframes pulseGlow {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.4; transform: scale(0.9); }
}

.pulse-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #38bdf8;
    box-shadow: 0 0 10px #38bdf8;
    display: inline-block;
    animation: pulseGlow 1.4s ease-in-out infinite;
}

/* ── Scrollbars ─────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb {
    background: rgba(99, 115, 155, 0.3);
    border-radius: 100px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(99, 115, 155, 0.6); }

/* ── Form Wrap ──────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1.35rem !important;
}

[data-testid="stForm"]:focus-within {
    border-color: var(--border-hover) !important;
}

/* ── PDF Preview Image Frame ────────────────────────────────────── */
[data-testid="stImage"] img {
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-card) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
</style>
"""


def inject_theme():
    """Inject AutoCV custom dark design tokens and styles into Streamlit."""
    st.markdown(AUTOCV_CSS, unsafe_allow_html=True)


def sidebar_brand():
    """Render the studio header in the sidebar."""
    st.markdown(
        """
        <div class="sidebar-brand-box">
            <div class="brand-gem">✦</div>
            <div>
                <div class="brand-title">AutoCV</div>
                <span class="brand-badge">LaTeX AI Studio</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_row(label: str, ok: bool, ok_text: str = "Connected", bad_text: str = "Missing"):
    """Render a status indicator in the sidebar."""
    badge_cls = "ok" if ok else "bad"
    badge_text = ok_text if ok else bad_text
    st.markdown(
        f"""
        <div class="status-row-item">
            <span class="status-row-label">{label}</span>
            <span class="status-badge {badge_cls}">{badge_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = ""):
    """Render a page hero header."""
    sub_tag = f'<div class="hero-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="hero-box">
            <h1 class="hero-title">{title}</h1>
            {sub_tag}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_label(text: str):
    """Render a sub-section label."""
    st.markdown(f'<div class="sub-label">{text}</div>', unsafe_allow_html=True)


def divider_label(text: str):
    """Render an elegant separator with a central title."""
    st.markdown(
        f'<div class="divider-strip"><span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def file_chip(text: str):
    """Render a code-style chip with file info."""
    st.markdown(f'<span class="meta-chip">📄 {text}</span>', unsafe_allow_html=True)


def candidate_badge(is_candidate: bool):
    """Render status pill for candidate vs approved state."""
    if is_candidate:
        st.markdown(
            '<span class="candidate-pill">⚡ Unapproved AI Candidate</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="approved-pill">✓ Approved Version</span>',
            unsafe_allow_html=True,
        )
