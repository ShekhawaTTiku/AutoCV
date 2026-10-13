"""Focused automated fallback, retry, and schema unit tests for AutoCV AIClient."""
from copy import deepcopy
import json
import time
import unittest
from unittest.mock import patch

import httpx

from src.ai.client import AIClient, _clean_gemini_schema
from src.ai.schemas import ANALYSIS_SCHEMA, EDIT_SCHEMA, REPAIR_SCHEMA, validate_json
from src.config import Settings
from src.exceptions import OperationCancelled, ProviderError
from src.latex_parser import sections
from src.models import Project, Section, Usage
from src.project_io import read_project

SOURCE = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\section{Summary}\n"
    "Software Engineer\n"
    "\\section{Experience}\n"
    "Built distributed systems.\n"
    "\\end{document}\n"
)


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.project = read_project("resume.tex", SOURCE.encode())
        self.settings = Settings(
            gemini_api_key="gemini-key",
            gemini_model="gemini-3.6-flash",
            gemini_fallback_model="gemini-3.8-flash",
            mistral_api_key="mistral-key",
            mistral_model="mistral-small-2603",
            overall_deadline=120,
            ai_timeout=30,
            max_retries=2,
        )
        self.usage = Usage(20, 120000)
        self.target_id = sections(self.project)[0].id

    def test_clean_gemini_schema(self):
        """Verify _clean_gemini_schema recursively removes additionalProperties while preserving required/properties."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sub": {
                    "type": "object",
                    "properties": {"val": {"type": "string"}},
                    "required": ["val"],
                    "additionalProperties": False,
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        }
        original_copy = deepcopy(schema)
        cleaned = _clean_gemini_schema(schema)

        # Original was not mutated
        self.assertEqual(schema, original_copy)
        self.assertIn("additionalProperties", schema)

        # Cleaned schema has no additionalProperties anywhere
        self.assertNotIn("additionalProperties", cleaned)
        self.assertNotIn("additionalProperties", cleaned["properties"]["sub"])
        self.assertNotIn("additionalProperties", cleaned["properties"]["items"]["items"])
        self.assertEqual(cleaned["required"], ["name"])
        self.assertEqual(cleaned["properties"]["name"]["type"], "string")

    def test_primary_model_success(self):
        """Primary Gemini 3.6 Flash responds successfully on first attempt."""
        calls = []

        def respond(request):
            calls.append((request.url.host, str(request.url.path)))
            payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
            return httpx.Response(
                200,
                json={
                    "usageMetadata": {"totalTokenCount": 80},
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
                },
            )

        client = AIClient(self.settings, httpx.MockTransport(respond))
        result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["section_id"], self.target_id)
        self.assertEqual(len(calls), 1)
        self.assertIn("gemini-3.6-flash", calls[0][1])

    def test_retry_followed_by_success(self):
        """Primary model suffers a transient 503 error, then retries with backoff and succeeds."""
        attempt = 0

        def respond(request):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                return httpx.Response(503, text="Service Unavailable")
            payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
            return httpx.Response(
                200,
                json={
                    "usageMetadata": {"totalTokenCount": 80},
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
                },
            )

        client = AIClient(self.settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(attempt, 2)

    def test_gemini_to_gemini_fallback(self):
        """gemini-3.6-flash fails across retries; client falls back to gemini-3.8-flash and succeeds."""
        called_models = []

        def respond(request):
            path = str(request.url.path)
            if "gemini-3.6-flash" in path:
                called_models.append("gemini-3.6-flash")
                return httpx.Response(500, text="Internal Server Error")
            if "gemini-3.8-flash" in path:
                called_models.append("gemini-3.8-flash")
                payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
                return httpx.Response(
                    200,
                    json={
                        "usageMetadata": {"totalTokenCount": 90},
                        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
                    },
                )
            return httpx.Response(404)

        client = AIClient(self.settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")
        self.assertIn("gemini-3.6-flash", called_models)
        self.assertIn("gemini-3.8-flash", called_models)

    def test_both_gemini_models_fail_mistral_succeeds(self):
        """Both Gemini models fail; client falls back to Mistral Small 4 and succeeds."""
        hosts = []

        def respond(request):
            hosts.append(request.url.host)
            if "googleapis" in request.url.host:
                return httpx.Response(502, text="Bad Gateway")
            # Mistral
            payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
            return httpx.Response(
                200,
                json={
                    "usage": {"total_tokens": 110},
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
                },
            )

        client = AIClient(self.settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")
        self.assertIn("api.mistral.ai", hosts)

    def test_quota_exhaustion_immediately_advances_to_next_model(self):
        """HTTP 429 with daily quota exhaustion triggers immediate model switch without wasting retries."""
        calls = []

        def respond(request):
            path = str(request.url.path)
            calls.append(path)
            if "gemini-3.6-flash" in path:
                return httpx.Response(429, json={"error": {"message": "RESOURCE_EXHAUSTED: Daily quota exceeded for free tier."}})
            if "gemini-3.8-flash" in path:
                payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
                return httpx.Response(
                    200,
                    json={
                        "usageMetadata": {"totalTokenCount": 60},
                        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
                    },
                )
            return httpx.Response(500)

        client = AIClient(self.settings, httpx.MockTransport(respond))
        result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")
        gemini_36_calls = [c for c in calls if "gemini-3.6-flash" in c]
        self.assertEqual(len(gemini_36_calls), 1)

    def test_missing_credentials_explains_mistral_unavailability(self):
        """When Mistral key is missing and all models fail, error explains Mistral was unavailable."""
        settings = Settings(
            gemini_api_key="gemini-key",
            gemini_model="gemini-3.6-flash",
            gemini_fallback_model="gemini-3.8-flash",
            mistral_api_key="",  # Missing!
            overall_deadline=120,
        )

        def respond(request):
            return httpx.Response(500, text="Internal error")

        client = AIClient(settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            with self.assertRaises(ProviderError) as cm:
                client.analyze("Update summary", self.project, self.usage)

        err_text = str(cm.exception)
        self.assertIn("MISTRAL_API_KEY is not configured", err_text)

    def test_invalid_json_or_schema_response(self):
        """Model returning invalid JSON or schema violation is treated as a failed attempt."""
        attempt = 0

        def respond(request):
            nonlocal attempt
            attempt += 1
            path = str(request.url.path)
            if "gemini-3.6-flash" in path:
                return httpx.Response(
                    200,
                    json={
                        "usageMetadata": {"totalTokenCount": 10},
                        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not a json string"}]}}],
                    },
                )
            payload = {"status": "ready", "section_id": self.target_id, "question": "", "proposals": []}
            return httpx.Response(
                200,
                json={
                    "usageMetadata": {"totalTokenCount": 40},
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}],
                },
            )

        client = AIClient(self.settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            result = client.analyze("Update summary", self.project, self.usage)

        self.assertEqual(result["status"], "ready")

    def test_overall_deadline_enforcement(self):
        """A tight overall deadline halts retries cleanly with a ProviderError."""
        settings = Settings(
            gemini_api_key="gemini-key",
            mistral_api_key="mistral-key",
            overall_deadline=1,
            ai_timeout=1,
            max_retries=2,
        )

        def respond(request):
            time.sleep(1.2)
            return httpx.Response(500, text="Slow error")

        client = AIClient(settings, httpx.MockTransport(respond))
        with self.assertRaises(ProviderError) as cm:
            client.analyze("Update summary", self.project, self.usage)

        self.assertIn("deadline", str(cm.exception).lower())

    def test_oversized_mistral_input_handling(self):
        """Mistral context adapter splits/chunks oversized prompts preserving document order."""
        client = AIClient(self.settings)
        large_sections = [
            {"id": f"sec-{i}", "title": f"Section {i}", "file": "main.tex", "preview": "x" * 500}
            for i in range(30)
        ]
        prompt = {"instruction": "Find something", "sections": large_sections}

        chunks = client._adapt_for_mistral(
            system="System instructions",
            prompt=prompt,
            schema=ANALYSIS_SCHEMA,
            output_limit=4096,
            max_budget=2000,
        )

        self.assertGreater(len(chunks), 1)
        combined_ids = [s["id"] for chunk in chunks for s in chunk["sections"]]
        expected_ids = [s["id"] for s in large_sections]
        self.assertEqual(combined_ids, expected_ids)

    def test_explicit_section_selection_bypasses_ai_detection(self):
        """Selecting a valid section from 'Target section (optional)' bypasses AI completely with no API calls."""
        unconfigured_settings = Settings(gemini_api_key="", mistral_api_key="", api_key="")

        def fail_on_request(request):
            self.fail("No HTTP request should be made when a section is explicitly selected!")

        client = AIClient(unconfigured_settings, httpx.MockTransport(fail_on_request))
        result = client.analyze("Update summary", self.project, self.usage, selected_section=self.target_id)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["section_id"], self.target_id)
        self.assertEqual(result["question"], "")
        self.assertEqual(result["proposals"], [])

    def test_explicit_section_selection_rejects_invalid_id(self):
        """Selecting a non-existent section raises a ProviderError asking to choose a valid section."""
        client = AIClient(self.settings)
        with self.assertRaises(ProviderError) as cm:
            client.analyze("Update summary", self.project, self.usage, selected_section="NonExistent-999")
        self.assertIn("Choose a section from the current resume", str(cm.exception))

    def test_graceful_failure_when_every_model_fails(self):
        """When every model in the fallback chain fails, returns ProviderError with details."""
        def respond(request):
            return httpx.Response(502, text="Gateway error")

        client = AIClient(self.settings, httpx.MockTransport(respond))
        with patch.object(client, "_interruptible_sleep", return_value=None):
            with self.assertRaises(ProviderError) as cm:
                client.analyze("Update summary", self.project, self.usage)

        self.assertIn("All configured AI models failed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
