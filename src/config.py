"""Application settings and environment configuration."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Mapping

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    model: str = "openai/gpt-oss-120b"
    compiler: str = ""
    compile_timeout: int = 90
    ai_timeout: int = 60
    request_limit: int = 20
    upload_mb: int = 10
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_model: str = "gemini-3.8-flash"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-2603"
    token_limit: int = 120000
    full_context_tokens: int = 12000
    max_output_tokens: int = 4096
    overall_deadline: int = 120
    max_retries: int = 2


def _resolve_compiler(preferred: str = "") -> str:
    """Find local or system LaTeX compiler; auto-download standalone Tectonic on Linux if missing."""
    if preferred and preferred.lower() not in {"", "auto"}:
        return preferred
    binary = ROOT / "tools" / ("tectonic.exe" if os.name == "nt" else "tectonic")
    if binary.exists():
        return str(binary)
    system_compiler = next(
        (path for name in ("tectonic", "pdflatex", "xelatex")
         if (path := shutil.which(name))), ""
    )
    if system_compiler:
        return system_compiler

    # Auto-provision portable Tectonic on Linux (e.g. Streamlit Community Cloud)
    if os.name != "nt":
        try:
            import io, platform, tarfile, urllib.request
            tools_dir = ROOT / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            machine = platform.machine().lower()
            pattern = "aarch64-unknown-linux-musl.tar.gz" if ("arm" in machine or "aarch64" in machine) else "x86_64-unknown-linux-musl.tar.gz"
            url = f"https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-{pattern}"
            req = urllib.request.Request(url, headers={"User-Agent": "AutoCV-CloudSetup"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("tectonic") and member.isfile():
                        extracted = tf.extractfile(member)
                        if extracted:
                            target = tools_dir / "tectonic"
                            target.write_bytes(extracted.read())
                            target.chmod(0o755)
                            return str(target)
        except Exception:
            pass
    return ""


def load_settings(secrets: Mapping | None = None) -> Settings:
    """Read this project's .env file; hosted Streamlit secrets can override it."""
    local = dotenv_values(ROOT / ".env")
    secrets = secrets or {}

    def value(name, default=""):
        return str(secrets.get(name) or os.getenv(name) or local.get(name) or default).strip()

    def positive(name, default):
        try:
            number = int(value(name, default))
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive whole number.") from exc
        if number < 1:
            raise ValueError(f"{name} must be a positive whole number.")
        return number

    compiler = _resolve_compiler(value("LATEX_COMPILER"))

    return Settings(
        api_key=value("GROQ_API_KEY"), model=value("GROQ_MODEL", "openai/gpt-oss-120b"),
        compiler=compiler, compile_timeout=positive("COMPILE_TIMEOUT_SECONDS", 90),
        ai_timeout=positive("AI_TIMEOUT_SECONDS", 60),
        request_limit=positive("SESSION_REQUEST_LIMIT", 20), upload_mb=positive("MAX_UPLOAD_MB", 10),
        gemini_api_key=value("GEMINI_API_KEY"), gemini_model=value("GEMINI_MODEL", "gemini-3.6-flash"),
        gemini_fallback_model=value("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash"),
        mistral_api_key=value("MISTRAL_API_KEY"), mistral_model=value("MISTRAL_MODEL", "mistral-small-2603"),
        token_limit=positive("SESSION_TOKEN_LIMIT", 120000),
        full_context_tokens=positive("FULL_CONTEXT_TOKENS", 12000),
        max_output_tokens=positive("MAX_OUTPUT_TOKENS", 4096),
        overall_deadline=positive("AI_DEADLINE_SECONDS", 120),
        max_retries=positive("MAX_RETRIES_PER_MODEL", 2),
    )

