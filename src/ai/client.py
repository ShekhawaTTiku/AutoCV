"""Multi-agent client coordinating Gemini section analysis, Groq editing, and Mistral repairs."""
import json
import re
from urllib.parse import quote

import httpx

from src.ai.context import estimate_tokens, repair_context, text_sources
from src.ai.prompts import ANALYSIS_PROMPT, EDIT_PROMPT, REPAIR_PROMPT
from src.ai.schemas import ANALYSIS_SCHEMA, EDIT_SCHEMA, REPAIR_SCHEMA, validate_json
from src.exceptions import ProviderError, check_cancel
from src.latex_parser import sections
from src.models import EditResult


class AIClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def configured(self, provider: str) -> bool:
        return bool(self._configuration(provider)[0])

    def _configuration(self, provider: str):
        cfg = self.settings
        if provider == "Gemini":
            return cfg.gemini_api_key, cfg.gemini_model, "GEMINI_API_KEY"
        if provider == "Groq":
            return cfg.api_key, cfg.model, "GROQ_API_KEY"
        if provider == "Mistral":
            return cfg.mistral_api_key, cfg.mistral_model, "MISTRAL_API_KEY"
        raise ValueError(f"Unknown AI provider: {provider}")

    def _request(self, provider, system, prompt, schema, usage, cancel_event=None):
        check_cancel(cancel_event)
        key, model, key_name = self._configuration(provider)
        if not key:
            raise ProviderError(f"{provider} is not configured. Add {key_name} to this app's .env.")
        if "\n" in key or "\r" in key or not key.isascii() or not model.strip():
            raise ProviderError(f"Check the {provider} key and model configuration.")
        estimate = estimate_tokens(system + json.dumps(prompt, ensure_ascii=False) + json.dumps(schema)) + 256
        output_limit = usage.authorize(estimate, self.settings.max_output_tokens)
        accounted = False
        try:
            check_cancel(cancel_event)
            if provider == "Gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(model, safe="-") + ":generateContent"
                headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
                generation = {
                    "maxOutputTokens": output_limit,
                    "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}},
                }
                if model == "gemini-3.5-flash-lite":
                    generation["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
                body = {"systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
                        "generationConfig": generation}
            else:
                url = ("https://api.groq.com/openai/v1/chat/completions" if provider == "Groq"
                       else "https://api.mistral.ai/v1/chat/completions")
                headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
                body = {
                    "model": model, "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "resume_operation", "strict": True, "schema": schema}},
                    ("max_completion_tokens" if provider == "Groq" else "max_tokens"): output_limit,
                }
                if provider == "Mistral":
                    body["temperature"] = 0.1
            with httpx.Client(timeout=min(self.settings.ai_timeout, 120),
                              transport=self.transport, follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=body)
            data = None
            if response.status_code == 200:
                try:
                    data = response.json()
                    metadata = data.get("usageMetadata" if provider == "Gemini" else "usage") or {}
                    total = metadata.get("totalTokenCount" if provider == "Gemini" else "total_tokens")
                    exact = type(total) is int and total >= 0
                    usage.record(total if exact else estimate + output_limit, estimated=not exact)
                    accounted = True
                except (ValueError, TypeError, AttributeError):
                    pass
            check_cancel(cancel_event)
            if response.status_code != 200:
                reason = {401: "rejected the API key", 403: "denied access to the model",
                          429: "reached a rate limit or quota", 400: "rejected the model or request format",
                          404: "could not find the configured model"}.get(response.status_code, "is unavailable")
                raise ProviderError(f"{provider} {reason}. Check configuration or retry later.")
            try:
                if data is None:
                    raise ValueError("Unreadable provider response")
                if provider == "Gemini":
                    choice = data["candidates"][0]
                    if choice.get("finishReason") != "STOP":
                        raise ValueError("Incomplete Gemini response")
                    content = "".join(part.get("text", "") for part in choice["content"]["parts"] if not part.get("thought"))
                else:
                    choice = data["choices"][0]
                    if choice.get("finish_reason") != "stop":
                        raise ValueError("Incomplete response")
                    content = choice["message"]["content"]
                    if isinstance(content, list):
                        content = "".join(part.get("text", "") for part in content)
                result = json.loads(content)
                validate_json(result, schema)
                return result
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                raise ProviderError(f"{provider} returned an incomplete or invalid response.") from None
        except httpx.TimeoutException:
            raise ProviderError(f"{provider} timed out. Your approved source is unchanged.") from None
        except httpx.HTTPError:
            raise ProviderError(f"Could not connect to {provider}. Check your connection and configuration.") from None
        finally:
            if not accounted:
                usage.record(estimate + output_limit, estimated=True)

    def analyze(self, instruction, project, usage, selected_section=None, cancel_event=None):
        available = sections(project)
        if not available:
            return {"status": "unsupported", "section_id": "", "question": "No safely bounded sections were found in this template.", "proposals": []}
        valid_ids = {item.id for item in available}
        if selected_section and selected_section not in valid_ids:
            raise ProviderError("Choose a section from the current resume.")
        source = text_sources(project)
        context = {
            "instruction": instruction, "selected_section": selected_section,
            "main_file": project.main_file,
            "sections": [{"id": s.id, "title": s.title, "file": s.file, "preview": s.content[:280]} for s in available],
        }
        if estimate_tokens(json.dumps(source, ensure_ascii=False)) <= self.settings.full_context_tokens:
            context["source_files"] = source
        else:
            context["source_omitted"] = True
            if selected_section:
                context["selected_section_body"] = next(s.content for s in available if s.id == selected_section)
        result = self._request("Gemini", ANALYSIS_PROMPT, context, ANALYSIS_SCHEMA, usage, cancel_event)
        if result["status"] == "ready":
            if result["section_id"] not in valid_ids or result["proposals"] or result["question"].strip():
                raise ProviderError("Gemini did not identify one valid section. Please clarify the target.")
            if selected_section and result["section_id"] != selected_section:
                return {"status": "clarification", "section_id": "", "proposals": [],
                        "question": "The instruction targets a different section. Select it or refine the instruction."}
        elif result["status"] == "split":
            if not 2 <= len(result["proposals"]) <= 20 or any(
                p["section_id"] not in valid_ids or not p["instruction"].strip() for p in result["proposals"]
            ):
                raise ProviderError("Gemini could not safely split the request. Ask for one section at a time.")
        elif not result["question"].strip():
            raise ProviderError("Gemini returned no clarification or limitation explanation.")
        return result

    def rewrite(self, instruction, section, usage, cancel_event=None):
        response = self._request("Groq", EDIT_PROMPT, {
            "instruction": instruction, "section_title": section.title, "section_body": section.content,
        }, EDIT_SCHEMA, usage, cancel_event)
        if response["status"] == "ready":
            if not response["text"].strip() or response["question"].strip():
                raise ProviderError("Groq did not return a valid section body.")
            text = response["text"]
            if "\n" not in text and r"\n" in text:
                text = text.replace(r"\r\n", "\n").replace(r"\n", "\n")
            response["text"] = re.sub(r"\\\\([A-Za-z@]+)", r"\\\1", text)
        elif response["text"].strip() or not response["question"].strip():
            raise ProviderError("Groq did not return a valid clarification.")
        return EditResult(**response)

    def repair(self, provider, project, approved, logs, usage, cancel_event=None, failed_attempts=None):
        if provider not in {"Groq", "Mistral"}:
            raise ValueError("Repair supports Groq and Mistral only.")
        context = repair_context(project, approved, logs, self.settings.full_context_tokens, failed_attempts)
        return self._request(provider, REPAIR_PROMPT, context, REPAIR_SCHEMA, usage, cancel_event)["patches"]
