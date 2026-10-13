"""UI package re-exporting state, lifecycle jobs, and interactive components."""
from src.ui.components import (
    download_buttons,
    open_project,
    preview,
    processing_status,
    settings,
)
from src.ui.state import Job, finish_job, initialize, reset, start_job
from src.ui.theme import (
    candidate_badge,
    divider_label,
    file_chip,
    inject_theme,
    page_header,
    section_label,
    sidebar_brand,
    status_row,
)

__all__ = [
    "Job",
    "initialize",
    "reset",
    "start_job",
    "finish_job",
    "settings",
    "processing_status",
    "open_project",
    "download_buttons",
    "preview",
    # Theme helpers
    "inject_theme",
    "sidebar_brand",
    "status_row",
    "page_header",
    "section_label",
    "divider_label",
    "file_chip",
    "candidate_badge",
]
