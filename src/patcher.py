"""Surgical patch application and validation for LaTeX repairs."""
from collections import Counter
from dataclasses import replace
from pathlib import PurePosixPath
import re

from src.constants import SECTION_COMMANDS, TEXT_EXTENSIONS
from src.exceptions import EditError
from src.latex_parser import _commands, _mask, _protected
from src.models import Project
from src.project_io import _decode


def _repair_skeleton(text: str) -> str:
    """Ignore syntax while retaining prose, names, dates, and numbers."""
    text = re.sub(r"\\(?:begin|end)\s*\{[A-Za-z*]+\}", "", text)
    text = re.sub(r"\\[A-Za-z@]+\*?", "", text)
    text = re.sub(r"\\([^A-Za-z])", r"\1", text)
    return "".join(re.sub(r"[{}\[\]$&^_~%]", "", text).split())


def apply_repair_patches(project: Project, patches: list[dict]) -> Project:
    """Validate and apply between 1 and 8 exact text patches to project files."""
    if not isinstance(patches, list) or not 1 <= len(patches) <= 8:
        raise EditError("A repair must contain between one and eight small patches.")
    files, total = dict(project.files), 0
    for patch in patches:
        if not isinstance(patch, dict) or set(patch) != {"file", "old_text", "new_text"}:
            raise EditError("The repair patch format is invalid.")
        name, old, new = patch["file"], patch["old_text"], patch["new_text"]
        if (not all(isinstance(value, str) for value in (name, old, new)) or
                name not in files or PurePosixPath(name).suffix.lower() not in TEXT_EXTENSIONS or
                not old or old == new or max(len(old), len(new)) > 1500):
            raise EditError("The repair must match a small excerpt of an existing source file.")
        total += len(old) + len(new)
        if total > 6000:
            raise EditError("The repair exceeds the 6,000-character limit.")
        content = _decode(files[name])
        newline = "\r\n" if b"\r\n" in files[name] else "\n"
        old = old.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        new = new.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        first = content.find(old)
        if first < 0 or content.find(old, first + 1) >= 0:
            raise EditError("The repair excerpt does not uniquely match the current source.")
        if _repair_skeleton(old) != _repair_skeleton(new):
            raise EditError("The proposed repair changes resume wording or facts.")
        if _protected(old) != _protected(new):
            raise EditError("The proposed repair changes layout or file dependencies.")
        old_sections = Counter(c for c, *_ in _commands(_mask(old)) if c in SECTION_COMMANDS)
        new_sections = Counter(c for c, *_ in _commands(_mask(new)) if c in SECTION_COMMANDS)
        if old_sections != new_sections:
            raise EditError("The repair cannot add or remove resume sections.")
        updated = content[:first] + new + content[first + len(old):]
        data = updated.encode("utf-8")
        if files[name].startswith(b"\xef\xbb\xbf"):
            data = b"\xef\xbb\xbf" + data
        files[name] = data
    return replace(project, files=files)
