"""AutoCV Core Engine Facade.

Re-exports all domain models, parsers, compilers, and workflow pipelines
for clean backward compatibility.
"""
from src.config import ROOT, Settings, load_settings
from src.constants import (
    MAX_EXTRACTED,
    MAX_FILES,
    MAX_LOG,
    MAX_UPLOAD,
    PROTECTED,
    SECTION_COMMANDS,
    TEXT_EXTENSIONS,
)
from src.compiler import (
    _ensure_graphic_assets,
    _kill_tree,
    _make_dummy_graphic,
    _preflight,
    compile_project,
)
from src.exceptions import (
    CompileError,
    EditError,
    OperationCancelled,
    ProjectError,
    UsageError,
    check_cancel,
)
from src.latex_parser import (
    _commands,
    _group,
    _mask,
    _profile,
    _protected,
    replace_section,
    sections,
)
from src.models import (
    EditResult,
    Outcome,
    Project,
    Section,
    Usage,
)
from src.orchestrator import (
    compiled_candidate,
    edit_candidate,
    repair_cycle,
)
from src.patcher import (
    _repair_skeleton,
    apply_repair_patches,
)
from src.pdf import (
    _pdf_lock,
    page_count,
    render_page,
)
from src.project_io import (
    _decode,
    _safe_path,
    project_zip,
    read_project,
    select_main,
    source_bytes,
    source_fingerprint,
)
from src.ai.context import estimate_tokens

__all__ = [
    "ROOT",
    "Settings",
    "load_settings",
    "page_count",
    "render_page",
    "_pdf_lock",
    "MAX_UPLOAD",
    "MAX_EXTRACTED",
    "MAX_FILES",
    "MAX_LOG",
    "SECTION_COMMANDS",
    "PROTECTED",
    "TEXT_EXTENSIONS",
    "ProjectError",
    "EditError",
    "CompileError",
    "OperationCancelled",
    "UsageError",
    "check_cancel",
    "estimate_tokens",
    "Usage",
    "Project",
    "Section",
    "_safe_path",
    "_decode",
    "read_project",
    "select_main",
    "_mask",
    "_commands",
    "_group",
    "sections",
    "_profile",
    "_protected",
    "replace_section",
    "source_bytes",
    "source_fingerprint",
    "_repair_skeleton",
    "apply_repair_patches",
    "project_zip",
    "_preflight",
    "_kill_tree",
    "_make_dummy_graphic",
    "_ensure_graphic_assets",
    "compile_project",
    "Outcome",
    "compiled_candidate",
    "repair_cycle",
    "edit_candidate",
    "EditResult",
]
