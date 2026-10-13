"""Core domain dataclasses and models."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
from src.exceptions import UsageError


@dataclass
class Usage:
    request_limit: int
    token_limit: int
    requests_used: int = 0
    tokens_used: int = 0
    estimated: bool = False
    _lock: object = field(default_factory=threading.Lock, repr=False)

    def authorize(self, input_estimate: int, output_limit: int) -> int:
        with self._lock:
            if self.requests_used >= self.request_limit:
                raise UsageError(
                    "The session AI request limit has been reached. Your approved source is available to download."
                )
            available = self.token_limit - self.tokens_used - input_estimate
            if available < 256:
                raise UsageError("The remaining token budget is insufficient for this provider request.")
            self.requests_used += 1
            return min(output_limit, available)

    def record(self, total: int, estimated: bool = False):
        with self._lock:
            self.tokens_used += max(0, int(total))
            self.estimated = self.estimated or estimated

    def snapshot(self) -> tuple[int, int, bool]:
        with self._lock:
            return self.requests_used, self.tokens_used, self.estimated


@dataclass(frozen=True)
class Project:
    name: str
    files: dict[str, bytes]
    tex_files: list[str]
    main_file: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "files", dict(self.files))
        object.__setattr__(self, "tex_files", list(self.tex_files))


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    start: int
    end: int
    content: str
    file: str


@dataclass
class Outcome:
    status: str
    message: str = ""
    project: Project | None = None
    pdf: bytes | None = None
    fingerprint: str | None = None
    question: str = ""
    proposals: list = field(default_factory=list)
    log: str = ""
    repairable: bool = False
    diagnostics: list = field(default_factory=list)


@dataclass(frozen=True)
class EditResult:
    status: str
    text: str
    question: str
