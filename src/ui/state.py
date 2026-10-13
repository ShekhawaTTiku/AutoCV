"""Streamlit session state management, background threading, and job lifecycle."""
from dataclasses import dataclass, field
from threading import Event, Thread
from uuid import uuid4

import streamlit as st

from src.ai import AIClient
from src.exceptions import (
    CompileError,
    EditError,
    OperationCancelled,
    ProviderError,
    UsageError,
)
from src.models import Outcome, Usage
from src.orchestrator import compiled_candidate, edit_candidate, repair_cycle
from src.project_io import source_fingerprint


@dataclass
class Job:
    kind: str
    base_id: str
    base_hash: str
    generation: int
    instruction: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    cancelled: Event = field(default_factory=Event)
    done: Event = field(default_factory=Event)
    stage: str = "Starting…"
    result: Outcome | None = None

    def progress(self, message: str):
        self.stage = message


def initialize(cfg):
    """Ensure all required session state keys and usage budgets are populated."""
    defaults = {
        "project": None, "history": [], "current": 0, "candidate": None,
        "question": "", "proposals": [], "notice": "", "error": "", "log": "",
        "repair_baseline": None, "job": None, "uploader_generation": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "usage" not in st.session_state:
        st.session_state.usage = Usage(
            cfg.request_limit, cfg.token_limit,
            requests_used=st.session_state.get("requests", 0),
        )
    usage = st.session_state.usage
    with usage._lock:
        usage.request_limit, usage.token_limit = cfg.request_limit, cfg.token_limit
    for snapshot in st.session_state.history:
        snapshot.setdefault("id", uuid4().hex)
        snapshot.setdefault("fingerprint", source_fingerprint(snapshot["project"]))
    candidate = st.session_state.candidate
    if candidate:
        candidate.setdefault("fingerprint", source_fingerprint(candidate["project"]))
        candidate.setdefault("status", "ready" if candidate.get("pdf") else "failed")
    if st.session_state.pop("clear_editor", False):
        st.session_state.instruction = ""
        st.session_state.clarification = ""
    if st.session_state.pop("clear_clarification", False):
        st.session_state.clarification = ""


def reset():
    """Cancel any active background thread and reset the entire session."""
    if st.session_state.job:
        st.session_state.job.cancelled.set()
    generation = st.session_state.uploader_generation + 1
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state.uploader_generation = generation


def start_job(kind: str, approved: dict, cfg, instruction: str = "", selected=None, baseline=None):
    """Launch background job thread for compiling, editing, or repairing."""
    if st.session_state.job:
        return
    job = Job(
        kind, approved["id"], source_fingerprint(approved["project"]),
        st.session_state.uploader_generation, instruction,
    )
    try:
        import ai
        client_cls = getattr(ai, "AIClient", AIClient)
    except ImportError:
        client_cls = AIClient
    client, usage = client_cls(cfg), st.session_state.usage
    st.session_state.job = job
    st.session_state.notice = ""
    st.session_state.error = ""
    st.session_state.question = ""
    st.session_state.proposals = []
    if kind == "edit":
        st.session_state.repair_baseline = None
        st.session_state.log = ""

    def work():
        try:
            if kind == "initial":
                job.progress("Compiling your uploaded LaTeX…")
                job.result = compiled_candidate(approved["project"], cfg, job.cancelled)
            elif kind == "repair":
                if not baseline:
                    raise ValueError("No compilation error is available to repair.")
                job.result = repair_cycle(
                    baseline["project"], approved["project"],
                    baseline["log"], client, cfg, usage,
                    job.cancelled, manual=True, progress=job.progress,
                )
            else:
                job.result = edit_candidate(
                    approved["project"], instruction, client, cfg,
                    usage, selected, job.cancelled, job.progress,
                )
        except OperationCancelled:
            job.result = Outcome("cancelled", "Request stopped. Partial output was discarded; your approved source is unchanged.")
        except CompileError as exc:
            job.result = Outcome("failed", str(exc), project=approved["project"],
                                 log=exc.log or str(exc), repairable=exc.repairable)
        except (ProviderError, UsageError, EditError) as exc:
            job.result = Outcome("failed", str(exc))
        except Exception:
            job.result = Outcome("failed", "An internal error prevented this operation. Your approved source is unchanged.")
        finally:
            job.done.set()

    Thread(target=work, daemon=True, name="resume-" + job.id[:8]).start()


def finish_job(job: Job):
    """Process completed job result and update session state."""
    if st.session_state.job is not job:
        return
    history = st.session_state.history
    current = st.session_state.current
    st.session_state.job = None
    if (job.generation != st.session_state.uploader_generation or not history or
            history[current]["id"] != job.base_id or
            source_fingerprint(history[current]["project"]) != job.base_hash):
        st.session_state.error = "The source version changed while processing. The late result was discarded."
        return
    outcome = job.result
    if job.cancelled.is_set() or (outcome and outcome.status == "cancelled"):
        st.session_state.candidate = None
        st.session_state.notice = "Request stopped. Partial output was discarded; your approved source is unchanged."
        return
    if outcome is None:
        st.session_state.error = "The operation stopped without producing a result."
        return
    if outcome.status == "ready":
        if (not outcome.pdf or not outcome.project or
                outcome.fingerprint != source_fingerprint(outcome.project)):
            st.session_state.error = "The PDF does not match the candidate source. The result was discarded."
            return
        if job.kind == "initial":
            history[current]["pdf"] = outcome.pdf
            history[current]["fingerprint"] = outcome.fingerprint
        else:
            st.session_state.candidate = {
                "id": uuid4().hex, "base_id": job.base_id, "project": outcome.project,
                "pdf": outcome.pdf, "fingerprint": outcome.fingerprint,
                "status": "ready",
                "label": job.instruction[:80] or "Compilation repair",
            }
        st.session_state.repair_baseline = None
        st.session_state.log = ""
        st.session_state.notice = outcome.message or "PDF preview is ready."
    elif outcome.status == "clarification":
        st.session_state.question = outcome.question
        st.session_state.clear_clarification = True
    elif outcome.status == "split":
        st.session_state.proposals = outcome.proposals
        st.session_state.notice = "Choose one section edit to run first."
    else:
        st.session_state.error = outcome.message or outcome.question or "This request could not finish."
        if outcome.log:
            st.session_state.log = outcome.log
        if outcome.repairable and outcome.project:
            st.session_state.repair_baseline = {"project": outcome.project, "log": outcome.log,
                                                "base_id": job.base_id}
        st.session_state.candidate = None
