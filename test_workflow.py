"""Focused routing/repair checks. Run with: python -B test_workflow.py"""
from copy import deepcopy
import json
from pathlib import Path
from threading import Event
import time
import unittest
from unittest.mock import patch

import httpx
import pymupdf
from streamlit.testing.v1 import AppTest

from ai import AIClient, EditResult, ProviderError, repair_context
from core import (
    CompileError, EditError, OperationCancelled, Project, Settings, Usage,
    UsageError, apply_repair_patches, compiled_candidate, edit_candidate,
    read_project, repair_cycle, sections, source_bytes, source_fingerprint,
)

ROOT = Path(__file__).resolve().parent
SOURCE = "\\documentclass{article}\n\\begin{document}\n\\section{Summary}\n\\textbf{Engineer}\n\\section{Skills}\nPython\n\\end{document}\n"
BROKEN = SOURCE.replace("\\textbf{Engineer}", "\\textbff{Engineer}")
PATCH = [{"file": "resume.tex", "old_text": "\\textbff{Engineer}", "new_text": "\\textbf{Engineer}"}]
with pymupdf.open() as doc:
    doc.new_page().insert_text((50, 50), "Test resume")
    PDF = doc.tobytes()
CFG = Settings(api_key="groq-test", gemini_api_key="gemini-test", mistral_api_key="mistral-test", compiler="test-compiler")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.sent = []
        self.actions = {"Groq": PATCH, "Mistral": PATCH}
        self.enabled = {"Groq", "Mistral"}
        self.analysis_status = "ready"

    def configured(self, provider):
        return provider in self.enabled

    def analyze(self, instruction, project, usage, selected=None, cancel_event=None):
        self.calls.append("Gemini")
        usage.authorize(100, 1000)
        usage.record(120)
        available = sections(project)
        if self.analysis_status == "split":
            return {"status": "split", "section_id": "", "question": "", "proposals": [
                {"section_id": s.id, "instruction": "Edit " + s.title} for s in available]}
        if self.analysis_status == "clarification":
            return {"status": "clarification", "section_id": "", "question": "Which section?", "proposals": []}
        return {"status": "ready", "section_id": selected or available[0].id, "question": "", "proposals": []}

    def rewrite(self, instruction, section, usage, cancel_event=None):
        self.calls.append("Groq edit")
        usage.authorize(100, 1000)
        usage.record(130)
        return EditResult("ready", section.content.replace("\\textbf", "\\textbff"), "")

    def repair(self, provider, project, approved, logs, usage, cancel_event=None, failed_attempts=None):
        usage.authorize(100, 1000)
        usage.record(140)
        self.calls.append(provider)
        self.sent.append({"provider": provider, "source": source_bytes(project),
                          "logs": deepcopy(logs), "failed": deepcopy(failed_attempts)})
        action = self.actions[provider]
        if callable(action):
            return action(cancel_event)
        if isinstance(action, Exception):
            raise action
        return deepcopy(action)


def good_compiler(project, command, timeout, cancel_event=None):
    return PDF


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.original = read_project("resume.tex", SOURCE.encode())
        self.baseline = read_project("resume.tex", BROKEN.encode())
        self.client = FakeClient()
        self.usage = Usage(20, 120000)

    def cycle(self, **kwargs):
        return repair_cycle(self.baseline, self.original, "Undefined control sequence: textbff", self.client,
                            CFG, self.usage, compiler=kwargs.pop("compiler", good_compiler), **kwargs)

    def test_groq_success_never_calls_mistral_or_changes_approved(self):
        before = source_fingerprint(self.original)
        outcome = self.cycle()
        self.assertEqual(self.client.calls, ["Groq"])
        self.assertEqual(outcome.status, "ready")
        self.assertEqual(source_bytes(outcome.project), SOURCE.encode())
        self.assertEqual(outcome.fingerprint, source_fingerprint(outcome.project))
        self.assertEqual(source_fingerprint(self.original), before)

    def test_groq_provider_failure_mistral_succeeds(self):
        self.client.actions["Groq"] = ProviderError("Groq quota exhausted")
        outcome = self.cycle()
        self.assertEqual(self.client.calls, ["Groq", "Mistral"])
        self.assertEqual(outcome.status, "ready")
        self.assertEqual(self.usage.requests_used, 2)
        self.assertEqual(source_bytes(self.original), SOURCE.encode())

    def test_invalid_groq_patch_fallback_receives_clean_baseline(self):
        self.client.actions["Groq"] = [{"file": "resume.tex", "old_text": "Engineer", "new_text": "Doctor"}]
        outcome = self.cycle()
        self.assertEqual(outcome.status, "ready")
        self.assertEqual(self.client.sent[1]["source"], BROKEN.encode())
        self.assertEqual(self.client.calls, ["Groq", "Mistral"])

    def test_valid_groq_patch_failed_compile_mistral_fresh_attempt(self):
        attempts = []
        def compiler(project, command, timeout, cancel_event=None):
            attempts.append(source_bytes(project))
            if len(attempts) == 1:
                raise CompileError("Still failing", "Groq repair line 4 failed")
            return PDF
        outcome = self.cycle(compiler=compiler)
        self.assertEqual(outcome.status, "ready")
        self.assertEqual(self.client.calls, ["Groq", "Mistral"])
        self.assertEqual(self.client.sent[1]["source"], BROKEN.encode())
        self.assertIn("Groq repair line 4 failed", self.client.sent[1]["logs"][1]["log"])
        self.assertEqual(attempts, [SOURCE.encode(), SOURCE.encode()])

    def test_both_providers_fail_without_retry_loop(self):
        self.client.actions = {name: ProviderError("Unavailable") for name in ("Groq", "Mistral")}
        outcome = self.cycle()
        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(outcome.pdf)
        self.assertEqual(self.client.calls, ["Groq", "Mistral"])
        self.assertEqual(source_bytes(self.original), SOURCE.encode())

    def test_invalid_mistral_patch_rejected(self):
        self.client.actions["Groq"] = ProviderError("Unavailable")
        self.client.actions["Mistral"] = [{"file": "resume.tex", "old_text": "Engineer", "new_text": "CEO"}]
        outcome = self.cycle()
        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(outcome.pdf)
        self.assertEqual(source_bytes(self.baseline), BROKEN.encode())

    def test_missing_mistral_configuration_never_calls_it(self):
        self.client.actions["Groq"] = ProviderError("Unavailable")
        self.client.enabled.remove("Mistral")
        outcome = self.cycle()
        self.assertEqual(self.client.calls, ["Groq"])
        self.assertIn("not configured", outcome.message)

    def test_budget_exhaustion_prevents_fallback_request(self):
        self.usage.request_limit = 1
        self.client.actions["Groq"] = ProviderError("Unavailable")
        outcome = self.cycle()
        self.assertEqual(self.client.calls, ["Groq"])
        self.assertEqual(self.usage.requests_used, 1)
        self.assertEqual(outcome.diagnostics[-1]["category"], "budget_exhausted")

    def test_cancellation_before_fallback(self):
        cancelled = Event()
        def fail(event):
            event.set()
            raise ProviderError("Primary failed")
        self.client.actions["Groq"] = fail
        with self.assertRaises(OperationCancelled):
            self.cycle(cancel_event=cancelled)
        self.assertEqual(self.client.calls, ["Groq"])

    def test_manual_button_path_calls_mistral_directly(self):
        outcome = self.cycle(manual=True)
        self.assertEqual(self.client.calls, ["Mistral"])
        self.assertEqual(outcome.status, "ready")

    def test_internal_programming_error_never_falls_back(self):
        self.client.actions["Groq"] = RuntimeError("Internal bug")
        with self.assertRaises(RuntimeError):
            self.cycle()
        self.assertEqual(self.client.calls, ["Groq"])

    def test_cancel_during_compilation_discards_pdf_without_fallback(self):
        event = Event()
        def compiler(project, command, timeout, cancel_event=None):
            event.set()
            return PDF
        with self.assertRaises(OperationCancelled):
            self.cycle(cancel_event=event, compiler=compiler)
        self.assertEqual(self.client.calls, ["Groq"])

    def test_source_fingerprint_rejects_stale_pdf(self):
        def compiler(project, command, timeout, cancel_event=None):
            project.files["resume.tex"] += b"% changed"
            return PDF
        with self.assertRaises(RuntimeError):
            self.cycle(compiler=compiler)
        self.assertEqual(source_bytes(self.original), SOURCE.encode())

    def test_gemini_then_groq_then_automatic_repair(self):
        compiled = []
        def compiler(project, command, timeout, cancel_event=None):
            compiled.append(source_bytes(project))
            if b"textbff" in source_bytes(project):
                raise CompileError("Undefined macro", "resume.tex:4 textbff")
            return PDF
        outcome = edit_candidate(self.original, "Improve summary", self.client, CFG, self.usage, compiler=compiler)
        self.assertEqual(self.client.calls, ["Gemini", "Groq edit", "Groq"])
        self.assertEqual(outcome.status, "ready")
        self.assertEqual(len(compiled), 2)
        self.assertEqual(source_bytes(self.original), SOURCE.encode())

    def test_clarification_and_split_never_call_groq(self):
        for status in ("clarification", "split"):
            self.client.calls.clear()
            self.client.analysis_status = status
            outcome = edit_candidate(self.original, "Vague request", self.client, CFG, self.usage, compiler=good_compiler)
            self.assertEqual(outcome.status, status)
            self.assertEqual(self.client.calls, ["Gemini"])
            self.assertIsNone(outcome.pdf)

    def test_repair_context_includes_styles_assets_logs_and_approved_comparison(self):
        baseline = Project("resume.zip", {**self.baseline.files, "custom.sty": b"\\ProvidesPackage{custom}",
                                          "refs.bib": b"@article{reference}", "images/logo.png": b"binary asset"}, ["resume.tex"], "resume.tex")
        context = repair_context(baseline, self.original, [{"origin": "baseline", "log": "resume.tex:4 failed"}], 12000)
        self.assertIn("custom.sty", context["source_files"])
        self.assertIn("refs.bib", context["source_files"])
        self.assertIn("resume.tex", context["approved_comparison"])
        self.assertIn("images/logo.png", [item["file"] for item in context["project_assets"]])

    def test_patch_limits_and_dependency_changes_remain_blocked(self):
        for patches in (PATCH * 9, [{"file": "resume.tex", "old_text": "Engineer", "new_text": "\\input{/secret}Engineer"}],
                        [{"file": "missing.tex", "old_text": "x", "new_text": "x}"}],
                        [{"file": "resume.tex", "old_text": "x" * 1501, "new_text": "x" * 1501 + "}"}]):
            with self.subTest(patches=patches), self.assertRaises(EditError):
                apply_repair_patches(self.baseline, patches)


class ProviderTests(unittest.TestCase):
    def test_invalid_groq_json_falls_back_once_with_clean_full_context(self):
        requests = []
        project = read_project("resume.tex", BROKEN.encode())
        approved = read_project("resume.tex", SOURCE.encode())
        def respond(request):
            requests.append(request)
            text = "invalid JSON" if "groq" in request.url.host else json.dumps({"patches": PATCH})
            return httpx.Response(200, json={"usage": {"total_tokens": 50}, "choices": [{
                "finish_reason": "stop", "message": {"content": text}}]})
        usage = Usage(20, 120000)
        client = AIClient(CFG, httpx.MockTransport(respond))
        outcome = repair_cycle(project, approved, "resume.tex:4 failed", client, CFG, usage, compiler=good_compiler)
        self.assertEqual(outcome.status, "ready")
        self.assertEqual([r.url.host for r in requests], ["api.groq.com", "api.mistral.ai"])
        context = json.loads(json.loads(requests[1].content)["messages"][1]["content"])
        self.assertEqual(context["source_files"]["resume.tex"], BROKEN)
        self.assertEqual(usage.snapshot(), (2, 100, False))

    def test_cancelled_response_keeps_exact_reported_usage(self):
        event = Event()
        def respond(request):
            event.set()
            return httpx.Response(200, json={"usage": {"total_tokens": 42}, "choices": [{
                "finish_reason": "stop", "message": {"content": json.dumps({"patches": PATCH})}}]})
        usage = Usage(20, 120000)
        client = AIClient(CFG, httpx.MockTransport(respond))
        project = read_project("resume.tex", BROKEN.encode())
        with self.assertRaises(OperationCancelled):
            client.repair("Mistral", project, project, [], usage, event)
        self.assertEqual(usage.snapshot(), (1, 42, False))

    def test_real_provider_payloads_route_gemini_groq_mistral_and_count_usage_once(self):
        project = read_project("resume.tex", BROKEN.encode())
        target = sections(project)[0]
        requests = []
        def respond(request):
            payload = json.loads(request.content)
            requests.append((request.url.host, payload))
            if "googleapis" in request.url.host:
                result = {"status": "ready", "section_id": target.id, "question": "", "proposals": []}
                return httpx.Response(200, json={"usageMetadata": {"totalTokenCount": 50}, "candidates": [{
                    "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}]})
            if "groq" in request.url.host:
                result = {"status": "ready", "text": "\nEngineer\n", "question": ""}
            else:
                result = {"patches": PATCH}
            return httpx.Response(200, json={"usage": {"total_tokens": 60}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]})
        usage = Usage(20, 120000)
        client = AIClient(CFG, httpx.MockTransport(respond))
        client.analyze("Improve summary", project, usage)
        client.rewrite("Improve summary", target, usage)
        client.repair("Mistral", project, project, [{"origin": "baseline", "log": "error"}], usage)
        self.assertEqual([host for host, _ in requests], ["generativelanguage.googleapis.com", "api.groq.com", "api.mistral.ai"])
        self.assertIn("responseFormat", requests[0][1]["generationConfig"])
        self.assertIn("max_completion_tokens", requests[1][1])
        self.assertIn("max_tokens", requests[2][1])
        self.assertEqual(requests[2][1]["model"], "mistral-large-latest")
        self.assertEqual(usage.snapshot(), (3, 170, False))

    def test_missing_key_and_budget_fail_before_http(self):
        sent = []
        def respond(request):
            sent.append(request)
            return httpx.Response(500)
        project = read_project("resume.tex", BROKEN.encode())
        client = AIClient(Settings(), httpx.MockTransport(respond))
        with self.assertRaises(ProviderError):
            client.repair("Mistral", project, project, [], Usage(10, 100000))
        client = AIClient(CFG, httpx.MockTransport(respond))
        with self.assertRaises(UsageError):
            client.repair("Mistral", project, project, [], Usage(10, 1))
        self.assertFalse(sent)

    def test_provider_error_never_exposes_credentials_and_marks_estimated_usage(self):
        client = AIClient(CFG, httpx.MockTransport(lambda request: httpx.Response(429, json={"error": "secret-key-value"})))
        project = read_project("resume.tex", BROKEN.encode())
        usage = Usage(10, 100000)
        with self.assertRaises(ProviderError) as error:
            client.repair("Mistral", project, project, [], usage)
        self.assertNotIn("secret-key-value", str(error.exception))
        self.assertNotIn("mistral-test", str(error.exception))
        self.assertEqual(usage.requests_used, 1)
        self.assertTrue(usage.estimated)

    def test_cancellation_never_transmits_request(self):
        event = Event()
        event.set()
        usage = Usage(10, 100000)
        client = AIClient(CFG, httpx.MockTransport(lambda request: self.fail("Unexpected HTTP request")))
        project = read_project("resume.tex", BROKEN.encode())
        with self.assertRaises(OperationCancelled):
            client.repair("Mistral", project, project, [], usage, event)
        self.assertEqual(usage.requests_used, 0)


class StreamlitTests(unittest.TestCase):
    def button(self, app, label):
        return next(button for button in app.button if button.label == label)

    def settle(self, app):
        for _ in range(100):
            app.run()
            self.assertFalse(app.exception, [item.value for item in app.exception])
            job = app.session_state["job"]
            if job is None:
                return app
            job.done.wait(.05)
        self.fail("Background operation did not finish")

    def loaded(self, source=SOURCE):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
        self.assertFalse(app.exception)
        app.file_uploader[0].set_value(("resume.tex", source.encode(), "application/x-tex")).run()
        return self.settle(app)

    def test_manual_repair_button_uses_mistral_and_requires_explicit_approval(self):
        client = FakeClient()
        with patch("core.load_settings", return_value=CFG), patch("ai.AIClient", return_value=client), \
                patch("core.compile_project", side_effect=[CompileError("bad macro", "resume.tex:4 textbff"), PDF]):
            app = self.loaded(BROKEN)
            self.assertIsNotNone(app.session_state["repair_baseline"])
            self.button(app, "Try fix with Mistral").click().run()
            self.settle(app)
            self.assertEqual(client.calls, ["Mistral"])
            self.assertEqual(len(app.session_state["history"]), 1)
            self.assertEqual(source_bytes(app.session_state["history"][0]["project"]), BROKEN.encode())
            self.assertIsNotNone(app.session_state["candidate"])
            self.button(app, "Approve candidate").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state["history"]), 2)
            self.assertEqual(source_bytes(app.session_state["history"][1]["project"]), SOURCE.encode())

    def test_rejection_and_both_repair_failures_preserve_approved_history(self):
        client = FakeClient()
        with patch("core.load_settings", return_value=CFG), patch("ai.AIClient", return_value=client), \
                patch("core.compile_project", return_value=PDF):
            app = self.loaded()
            app.text_area(key="instruction").set_value("Rewrite Summary")
            self.button(app, "Apply changes").click().run()
            self.settle(app)
            self.assertEqual(client.calls[:2], ["Gemini", "Groq edit"])
            self.assertIsNotNone(app.session_state["candidate"])
            self.button(app, "Reject candidate").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(source_bytes(app.session_state["history"][0]["project"]), SOURCE.encode())
            self.assertEqual(len(app.session_state["history"]), 1)

    def test_stale_pdf_cannot_be_approved(self):
        client = FakeClient()
        with patch("core.load_settings", return_value=CFG), patch("ai.AIClient", return_value=client), \
                patch("core.compile_project", return_value=PDF):
            app = self.loaded()
            app.text_area(key="instruction").set_value("Rewrite Summary")
            self.button(app, "Apply changes").click().run()
            self.settle(app)
            candidate = app.session_state["candidate"]
            candidate["status"] = "failed"
            app.run()
            self.assertTrue(self.button(app, "Approve candidate").disabled)
            candidate["status"] = "ready"
            app.run()
            self.assertFalse(self.button(app, "Approve candidate").disabled)
            candidate["project"].files["resume.tex"] += b"% after compilation"
            app.run()
            self.assertTrue(self.button(app, "Approve candidate").disabled)
            self.assertEqual(len(app.session_state["history"]), 1)

    def test_both_automatic_repairs_fail_then_new_request_clears_stale_repair(self):
        client = FakeClient()
        client.actions = {provider: ProviderError("Unavailable") for provider in ("Groq", "Mistral")}
        def compiler(project, command, timeout, cancel_event=None):
            if b"textbff" in source_bytes(project):
                raise CompileError("Undefined macro", "resume.tex:4 textbff")
            return PDF
        with patch("core.load_settings", return_value=CFG), patch("ai.AIClient", return_value=client), \
                patch("core.compile_project", side_effect=compiler):
            app = self.loaded()
            app.text_area(key="instruction").set_value("Rewrite Summary")
            self.button(app, "Apply changes").click().run()
            self.settle(app)
            self.assertEqual(client.calls, ["Gemini", "Groq edit", "Groq", "Mistral"])
            self.assertIsNone(app.session_state["candidate"])
            self.assertIsNotNone(app.session_state["repair_baseline"])
            self.assertEqual(source_bytes(app.session_state["history"][0]["project"]), SOURCE.encode())
            client.analysis_status = "clarification"
            self.button(app, "Apply changes").click().run()
            self.settle(app)
            self.assertIsNone(app.session_state["repair_baseline"])
            self.assertEqual(app.session_state["log"], "")

    def test_cancel_button_waits_for_worker_and_discards_late_output(self):
        client = FakeClient()
        started, release = Event(), Event()
        analyze = client.analyze
        def blocked(instruction, project, usage, selected=None, cancel_event=None):
            started.set()
            release.wait(5)
            return analyze(instruction, project, usage, selected, cancel_event)
        client.analyze = blocked
        try:
            with patch("core.load_settings", return_value=CFG), patch("ai.AIClient", return_value=client), \
                    patch("core.compile_project", return_value=PDF):
                app = self.loaded()
                app.text_area(key="instruction").set_value("Rewrite Summary")
                self.button(app, "Apply changes").click().run()
                self.assertTrue(started.wait(1))
                self.button(app, "Cancel request").click().run()
                self.assertIsNotNone(app.session_state["job"])
                self.assertTrue(app.session_state["job"].cancelled.is_set())
                release.set()
                self.settle(app)
                self.assertIsNone(app.session_state["candidate"])
                self.assertEqual(client.calls, ["Gemini"])
                self.assertEqual(source_bytes(app.session_state["history"][0]["project"]), SOURCE.encode())
        finally:
            release.set()

    def test_mistral_is_optional_for_normal_editing(self):
        cfg = Settings(api_key="test-groq", gemini_api_key="test-gemini", compiler="test-compiler")
        client = FakeClient()
        with patch("core.load_settings", return_value=cfg), patch("ai.AIClient", return_value=client), \
                patch("core.compile_project", return_value=PDF):
            app = self.loaded()
            self.assertFalse(self.button(app, "Apply changes").disabled)
            app.text_area(key="instruction").set_value("Rewrite Summary")
            self.button(app, "Apply changes").click().run()
            self.settle(app)
            self.assertIsNotNone(app.session_state["candidate"])
            self.assertEqual(client.calls, ["Gemini", "Groq edit"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
