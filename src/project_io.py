"""Project filesystem extraction, sanitization, and packaging."""
from dataclasses import replace
import hashlib
import io
from pathlib import PurePosixPath, PureWindowsPath
import re
import stat
import zipfile

from src.constants import MAX_EXTRACTED, MAX_FILES, MAX_UPLOAD
from src.exceptions import ProjectError
from src.models import Project


def _safe_path(value: str) -> str:
    """Enforce strict sandbox rules on relative file paths inside projects."""
    value = value.replace("\\", "/")
    parts = value.split("/")
    if (not value or value.startswith("/") or PureWindowsPath(value).drive
            or any(p in {"", ".", ".."} for p in parts)):
        raise ProjectError("File paths must stay inside the uploaded project.")
    for part in parts:
        if (any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or part.endswith((" ", "."))
                or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)):
            raise ProjectError("The project contains an unsupported file name.")
    return "/".join(parts)


def _decode(data: bytes) -> str:
    """Decode UTF-8 source data while stripping optional UTF-8 BOM."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectError("LaTeX sources must use UTF-8 encoding.") from exc


def read_project(filename: str, data: bytes) -> Project:
    """Load a single .tex file or safely extract a ZIP LaTeX project."""
    if not data or len(data) > MAX_UPLOAD:
        raise ProjectError("Upload a nonempty .tex or ZIP file smaller than 20 MB.")
    filename = _safe_path(filename.replace("\\", "/").rsplit("/", 1)[-1])
    suffix = PurePosixPath(filename).suffix.lower()
    files: dict[str, bytes] = {}
    if suffix == ".tex":
        files[filename] = data
    elif suffix == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                if len(members) > MAX_FILES:
                    raise ProjectError("The ZIP contains too many files (maximum 500).")
                seen, total = set(), 0
                for member in members:
                    relative = _safe_path(member.filename.rstrip("/") if member.is_dir() else member.filename)
                    if relative.casefold() in seen:
                        raise ProjectError("The ZIP contains conflicting file names.")
                    seen.add(relative.casefold())
                    if stat.S_IFMT(member.external_attr >> 16) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise ProjectError("Links and special files are not supported.")
                    total += member.file_size
                    if (member.flag_bits & 1 or total > MAX_EXTRACTED
                            or member.file_size > 1024 * 1024 and member.file_size / max(member.compress_size, 1) > 200):
                        raise ProjectError("The ZIP is encrypted or exceeds safe extraction limits.")
                    if not member.is_dir():
                        files[relative] = archive.read(member)
                # A file cannot also be an ancestor directory of another file.
                names = {name.casefold() for name in files}
                if any("/".join(name.split("/")[:i]).casefold() in names
                       for name in files for i in range(1, len(name.split("/")))):
                    raise ProjectError("The ZIP contains conflicting file and folder names.")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
            raise ProjectError("The ZIP is invalid or uses unsupported compression.") from exc
    else:
        raise ProjectError("Upload a .tex file or a ZIP LaTeX project.")
    tex_files = sorted(name for name in files if name.lower().endswith(".tex"))
    if not tex_files:
        raise ProjectError("The project does not contain any .tex files.")
    for name in tex_files:
        _decode(files[name])
    return Project(filename, files, tex_files, tex_files[0] if len(tex_files) == 1 else None)


def select_main(project: Project, relative: str) -> Project:
    """Set the root compilation .tex file for a multi-file project."""
    relative = _safe_path(relative)
    if relative not in project.tex_files:
        raise ProjectError("Choose a main .tex file from this project.")
    return replace(project, main_file=relative)


def source_bytes(project: Project) -> bytes:
    """Return the raw bytes of the project's selected main .tex file."""
    if project.main_file is None or project.main_file not in project.files:
        raise ProjectError("Select a main .tex file first.")
    return project.files[project.main_file]


def source_fingerprint(project: Project) -> str:
    """Compute a SHA-256 hash across all files and filenames in the project."""
    digest = hashlib.sha256()
    for name, data in sorted(project.files.items()):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def project_zip(project: Project) -> bytes:
    """Pack the current state of all project files into a clean ZIP archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(project.files.items()):
            archive.writestr(_safe_path(name), content)
    return buffer.getvalue()
