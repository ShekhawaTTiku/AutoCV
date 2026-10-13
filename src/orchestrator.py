"""High-level orchestration of candidate creation, validation, compilation, and repair loops."""
from src.compiler import _preflight, compile_project
from src.exceptions import (
    CompileError,
    EditError,
    ProviderError,
    UsageError,
    check_cancel,
)
from src.config import Settings
from src.latex_parser import replace_section, sections
from src.models import Outcome, Project, Usage
from src.patcher import apply_repair_patches
from src.project_io import source_fingerprint


def compiled_candidate(project: Project, settings: Settings, cancel_event=None, compiler=None) -> Outcome:
    """Compile project into a candidate and verify fingerprint invariance."""
    check_cancel(cancel_event)
    before = source_fingerprint(project)
    if compiler is None:
        try:
            import core
            compiler = getattr(core, "compile_project", compile_project)
        except ImportError:
            compiler = compile_project
    pdf = compiler(project, settings.compiler, settings.compile_timeout, cancel_event=cancel_event)
    check_cancel(cancel_event)
    if not pdf or not pdf.startswith(b"%PDF-"):
        raise CompileError("The compiler did not return a valid PDF.")
    if before != source_fingerprint(project):
        raise RuntimeError("The source changed during compilation. No candidate can be approved.")
    return Outcome("ready", project=project, pdf=pdf, fingerprint=before)


def repair_cycle(baseline: Project, approved: Project, log: str, client, settings: Settings,
                 usage: Usage, cancel_event=None, manual: bool = False, progress=None, compiler=None) -> Outcome:
    """Run repair cycle: Groq first, then one Mistral fallback (or Mistral directly if manual)."""
    check_cancel(cancel_event)
    _preflight(baseline)
    baseline_hash = source_fingerprint(baseline)
    logs = [{"origin": "repair_baseline", "log": log}]
    attempts, diagnostics = [], []
    last_error = "No repair provider could complete this request."

    for provider in (("Mistral",) if manual else ("Groq", "Mistral")):
        check_cancel(cancel_event)
        if not client.configured(provider):
            last_error = f"{provider} repair is not configured. Add {provider.upper()}_API_KEY to .env."
            diagnostics.append({"provider": provider, "category": "not_configured"})
            continue
        if progress:
            progress(f"{provider}: repairing compilation errors…")
        proposed = None
        try:
            proposed = client.repair(provider, baseline, approved, logs, usage, cancel_event, attempts)
            check_cancel(cancel_event)
            revised = apply_repair_patches(baseline, proposed)
            if source_fingerprint(baseline) != baseline_hash:
                raise RuntimeError("The clean repair baseline changed.")
            if progress:
                progress(f"Compiling the {provider} repair…")
            outcome = compiled_candidate(revised, settings, cancel_event, compiler)
            outcome.message = f"{provider} repair compiled successfully. Review the PDF before approving."
            outcome.diagnostics = diagnostics + [{"provider": provider, "category": "compiled"}]
            return outcome
        except UsageError as exc:
            last_error = str(exc)
            diagnostics.append({"provider": provider, "category": "budget_exhausted"})
            break
        except ProviderError as exc:
            last_error = str(exc)
            diagnostics.append({"provider": provider, "category": "provider_error"})
            attempts.append({"provider": provider, "error": last_error})
        except EditError as exc:
            last_error = str(exc)
            diagnostics.append({"provider": provider, "category": "patch_rejected"})
            attempts.append({"provider": provider, "error": last_error})
        except CompileError as exc:
            last_error = str(exc)
            diagnostics.append({"provider": provider, "category": "compilation_failed"})
            logs.append({"origin": f"{provider}_repair", "log": exc.log or str(exc)})
            attempts.append({"provider": provider, "patches": proposed, "error": last_error})
            if not exc.repairable:
                break
        check_cancel(cancel_event)

    return Outcome(
        "failed",
        "Repair could not finish. " + last_error + " Your approved source is unchanged.",
        project=baseline,
        log="\n\n".join(item["origin"] + ":\n" + item["log"] for item in logs),
        repairable=True,
        diagnostics=diagnostics,
    )


def edit_candidate(project: Project, instruction: str, client, settings: Settings,
                   usage: Usage, selected_section=None, cancel_event=None,
                   progress=None, compiler=None) -> Outcome:
    """Full workflow: Gemini routing -> Groq editing -> candidate compilation -> repair if needed."""
    check_cancel(cancel_event)
    if progress:
        progress("Gemini: reading the original LaTeX and identifying the section…")
    analysis = client.analyze(instruction, project, usage, selected_section, cancel_event)
    check_cancel(cancel_event)
    if analysis["status"] != "ready":
        return Outcome(analysis["status"], question=analysis["question"], proposals=analysis["proposals"])
    target = next((s for s in sections(project) if s.id == analysis["section_id"]), None)
    if target is None:
        raise EditError("Gemini selected a section that is not in this approved version.")
    if progress:
        progress("Groq GPT-OSS: editing the selected section…")
    rewritten = client.rewrite(instruction, target, usage, cancel_event)
    check_cancel(cancel_event)
    if rewritten.status != "ready":
        return Outcome(rewritten.status, question=rewritten.question)
    revised = replace_section(project, target.id, rewritten.text)
    try:
        if progress:
            progress("Compiling the edit candidate…")
        outcome = compiled_candidate(revised, settings, cancel_event, compiler)
        outcome.message = "Candidate compiled successfully. Review it before approving."
        return outcome
    except CompileError as exc:
        if not exc.repairable:
            return Outcome("failed", str(exc), project=revised, log=exc.log or str(exc))
        return repair_cycle(revised, project, exc.log or str(exc), client, settings, usage,
                            cancel_event, progress=progress, compiler=compiler)
