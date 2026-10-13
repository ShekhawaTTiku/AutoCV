"""Context building, text source extraction, and repair payload generation."""
import json
import math
from src.constants import TEXT_EXTENSIONS
from src.exceptions import ProviderError
from src.project_io import source_fingerprint


def estimate_tokens(text: str) -> int:
    """Fast, safe heuristic for token estimation."""
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def text_sources(project) -> dict[str, str]:
    """Extract and decode all text-based source files from the project."""
    sources = {}
    for name, data in project.files.items():
        if name.lower().endswith(tuple(TEXT_EXTENSIONS)):
            try:
                sources[name] = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ProviderError(f"The source file {name} must use UTF-8.") from None
    return sources


def repair_context(project, approved, logs, threshold, failed_attempts=None) -> dict:
    """Build full project context for repair; prioritizes relevant files when exceeding token limits."""
    sources = text_sources(project)
    inventory = [{"file": name, "bytes": len(data)} for name, data in sorted(project.files.items())]
    context = {
        "main_file": project.main_file,
        "baseline_fingerprint": source_fingerprint(project),
        "source_files": sources,
        "project_assets": inventory,
        "compiler_logs": logs,
        "failed_attempts": failed_attempts or [],
        "approved_comparison": {
            name: text for name, text in text_sources(approved).items()
            if name in sources and text != sources[name]
        },
        "context_reduced": False,
    }
    if estimate_tokens(json.dumps(context, ensure_ascii=False)) > threshold:
        # Preserve full main source, every source named in a log, referenced
        # project dependencies, and custom styles/classes/bibliographies.
        log_text = "\n".join(item["log"] for item in logs)
        needed = {project.main_file}
        needed.update(name for name in sources if name in log_text or name.rsplit("/", 1)[-1] in log_text)
        needed.update(name for name in sources if not name.lower().endswith(".tex"))
        while True:
            selected_text = "\n".join(sources.get(name, "") for name in needed)
            referenced = {
                name for name in sources
                if name in selected_text or name.rsplit("/", 1)[-1] in selected_text
                or name.rsplit("/", 1)[-1].rsplit(".", 1)[0] in selected_text
            }
            extra = referenced - needed
            if not extra:
                break
            needed.update(extra)
        context["source_files"] = {name: content for name, content in sources.items() if name in needed}
        context["approved_comparison"] = {name: text for name, text in context["approved_comparison"].items() if name in needed}
        context["omitted_files"] = sorted(set(sources) - needed)
        context["context_reduced"] = True
    return context
