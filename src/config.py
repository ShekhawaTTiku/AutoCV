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
    gemini_model: str = "gemini-3.5-flash-lite"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    token_limit: int = 120000
    full_context_tokens: int = 12000
    max_output_tokens: int = 4096


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

    compiler = value("LATEX_COMPILER")
    if compiler.lower() in {"", "auto"}:
        binary = ROOT / "tools" / ("tectonic.exe" if os.name == "nt" else "tectonic")
        compiler = str(binary) if binary.exists() else next(
            (path for name in ("tectonic", "pdflatex", "xelatex")
             if (path := shutil.which(name))), "")

    return Settings(
        api_key=value("GROQ_API_KEY"), model=value("GROQ_MODEL", "openai/gpt-oss-120b"),
        compiler=compiler, compile_timeout=positive("COMPILE_TIMEOUT_SECONDS", 90),
        ai_timeout=positive("AI_TIMEOUT_SECONDS", 60),
        request_limit=positive("SESSION_REQUEST_LIMIT", 20), upload_mb=positive("MAX_UPLOAD_MB", 10),
        gemini_api_key=value("GEMINI_API_KEY"), gemini_model=value("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        mistral_api_key=value("MISTRAL_API_KEY"), mistral_model=value("MISTRAL_MODEL", "mistral-large-latest"),
        token_limit=positive("SESSION_TOKEN_LIMIT", 120000),
        full_context_tokens=positive("FULL_CONTEXT_TOKENS", 12000),
        max_output_tokens=positive("MAX_OUTPUT_TOKENS", 4096),
    )
