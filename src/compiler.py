"""LaTeX sandbox compilation, process lifetime control, and placeholder asset generation."""
import io
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from PIL import Image
import pymupdf

from src.constants import MAX_EXTRACTED, MAX_LOG, TEXT_EXTENSIONS
from src.exceptions import CompileError, ProjectError, check_cancel
from src.latex_parser import _mask
from src.models import Project
from src.project_io import _decode, _safe_path, source_bytes


def _preflight(project: Project):
    """Verify that source files do not escape the sandbox or use disallowed TeX primitives."""
    source_bytes(project)
    for name, content in project.files.items():
        _safe_path(name)
        if PurePosixPath(name).suffix.lower() not in TEXT_EXTENSIONS:
            continue
        source = _mask(_decode(content))
        if re.search(r"\\(?:write\s*18\b|directlua\b|latelua\b|luaexec\b|openin\b|openout\b|read\b|csname\b|catcode\b|special\b)|\^\^", source, re.I):
            raise ProjectError("This project requests unsupported file access or executable TeX commands.")
        for match in re.finditer(r"\\(?:input|include|includegraphics|bibliography|addbibresource|pdfximage)\s*(?:\[[^\]]*\]\s*)?(?:\{([^{}]*)\}|([^\s{}%]+))", source):
            target = (match.group(1) or match.group(2)).strip().strip('"').replace("\\", "/")
            if target.startswith(("/", "~", "|")) or PureWindowsPath(target).drive:
                raise ProjectError("LaTeX dependencies must use paths inside the uploaded project.")
            parts = list(PurePosixPath(project.main_file).parent.parts)
            for part in target.split("/"):
                if part == "..":
                    if not parts:
                        raise ProjectError("A LaTeX file reference escapes the uploaded project.")
                    parts.pop()
                elif part not in {"", "."}:
                    parts.append(part)


def _kill_tree(process):
    """Terminate the process and all spawned child processes."""
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def _make_dummy_graphic(ext: str) -> bytes:
    """Generate minimal valid image bytes so compilation doesn't fail on missing images."""
    ext = ext.lower()
    if ext in {".jpg", ".jpeg"}:
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100), color=(240, 240, 240)).save(buffer, format="JPEG")
        return buffer.getvalue()
    if ext == ".pdf":
        with pymupdf.open() as doc:
            doc.new_page(width=100, height=100)
            return doc.tobytes()
    buffer = io.BytesIO()
    Image.new("RGBA", (100, 100), color=(240, 240, 240, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _ensure_graphic_assets(project: Project, root: Path, main_parent: Path):
    """Generate blank placeholder files for any referenced images missing from upload."""
    for filename in project.tex_files:
        content = _decode(project.files[filename])
        source = _mask(content)
        for match in re.finditer(
            r"\\(?:includegraphics|pdfximage)\s*(?:\[[^\]]*\]\s*)?(?:\{([^{}]*)\}|([^\s{}%]+))",
            source,
        ):
            target = (match.group(1) or match.group(2)).strip().strip('"').replace("\\", "/")
            if not target or target.startswith(("/", "~", "|")) or PureWindowsPath(target).drive:
                continue
            rel_path = PurePosixPath(target)
            ext = rel_path.suffix.lower()
            if ext:
                candidates = [(target, ext)]
            else:
                candidates = [(target + ".png", ".png"), (target + ".jpg", ".jpg"), (target + ".pdf", ".pdf")]

            for candidate_rel, candidate_ext in candidates:
                for base_dir in (main_parent, root):
                    try:
                        dest = base_dir.joinpath(*candidate_rel.split("/"))
                        if not dest.exists():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(_make_dummy_graphic(candidate_ext))
                    except (OSError, ValueError):
                        pass


def compile_project(project: Project, command: str, timeout: int = 90, cancel_event=None) -> bytes:
    """Compile project into PDF in an isolated temporary directory with timeouts and strict security."""
    check_cancel(cancel_event)
    try:
        _preflight(project)
    except (ProjectError, OSError) as exc:
        raise CompileError(str(exc), repairable=False) from exc
    executable = str(Path(command).resolve()) if Path(command).is_file() else shutil.which(command)
    if not executable:
        raise CompileError("LaTeX compiler not found. Configure LATEX_COMPILER or install TeX Live.", repairable=False)
    engine = Path(executable).stem.lower()
    if engine not in {"tectonic", "pdflatex", "xelatex"}:
        raise CompileError("Choose tectonic, pdflatex, or xelatex as the compiler.", repairable=False)
    with tempfile.TemporaryDirectory(prefix="autocv-") as temporary:
        root, output = Path(temporary) / "source", Path(temporary) / "output"
        root.mkdir()
        output.mkdir()
        try:
            for name, content in project.files.items():
                path = root.joinpath(*name.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            main = root.joinpath(*project.main_file.split("/"))
            _ensure_graphic_assets(project, root, main.parent)
            args = ([executable, "-X", "compile", "--untrusted", "--keep-logs", "--outdir", str(output), "./" + main.name]
                    if engine == "tectonic" else
                    [executable, "-no-shell-escape", "-no-parse-first-line", "-interaction=nonstopmode",
                     "-halt-on-error", "-file-line-error", f"-output-directory={output}", "./" + main.name])
            env = {k: v for k, v in os.environ.items()
                   if not any(token in k.upper() for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
            env.update({"TECTONIC_UNTRUSTED_MODE": "1", "shell_escape": "0", "openout_any": "p",
                        "openin_any": "p", "TEXINPUTS": f"{root}//{os.pathsep}", "TEXMFOUTPUT": str(output)})
            options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                       if os.name == "nt" else {"start_new_session": True})
            process = subprocess.Popen(args, cwd=main.parent, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
            chunks, retained = [], [0]

            def drain():
                while chunk := process.stdout.read(8192):
                    room = MAX_LOG - retained[0]
                    if room > 0:
                        chunks.append(chunk[:room])
                        retained[0] += min(room, len(chunk))

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            timed_out = False
            try:
                deadline = time.monotonic() + max(1, min(timeout, 180))
                while process.poll() is None:
                    check_cancel(cancel_event)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        _kill_tree(process)
                        break
                    try:
                        process.wait(timeout=min(.2, remaining))
                    except subprocess.TimeoutExpired:
                        pass
            except BaseException:
                _kill_tree(process)
                reader.join(timeout=5)
                process.stdout.close()
                raise
            reader.join(timeout=5)
            if reader.is_alive():
                _kill_tree(process)
                reader.join(timeout=5)
            process.stdout.close()
            log = b"".join(chunks).decode("utf-8", errors="replace")
            for logfile in output.glob("*.log"):
                with logfile.open("rb") as stream:
                    log += "\n" + stream.read(max(0, MAX_LOG - len(log))).decode("utf-8", errors="replace")
            log = log.replace(str(Path(temporary)), "<temporary project>")[:MAX_LOG]
            if timed_out:
                raise CompileError("Compilation timed out. Try a smaller project or fix the LaTeX source.", log, repairable=False)
            check_cancel(cancel_event)
            pdf = output / (main.stem + ".pdf")
            if process.returncode or not pdf.is_file():
                raise CompileError("LaTeX compilation failed. Review the compiler log below.", log)
            if pdf.stat().st_size > MAX_EXTRACTED:
                raise CompileError("The generated PDF exceeds the 50 MB size limit.", log, repairable=False)
            data = pdf.read_bytes()
            if not data.startswith(b"%PDF-"):
                raise CompileError("The compiler did not produce a valid PDF.", log)
            return data
        except (OSError, subprocess.SubprocessError) as exc:
            raise CompileError("Unable to run the LaTeX compiler.", str(exc), repairable=False) from exc
