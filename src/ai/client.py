"""Multi-agent client coordinating Gemini section analysis, Groq editing, and Mistral repairs with automated fallback."""
from __future__ import annotations

import json
import logging
import random
import re
import time
from urllib.parse import quote

import httpx

from src.ai.context import estimate_tokens, repair_context, text_sources
from src.ai.prompts import ANALYSIS_PROMPT, EDIT_PROMPT, REPAIR_PROMPT
from src.ai.schemas import ANALYSIS_SCHEMA, EDIT_SCHEMA, REPAIR_SCHEMA, validate_json
from src.exceptions import OperationCancelled, ProviderError, check_cancel
from src.latex_parser import sections
from src.models import EditResult

logger = logging.getLogger("autocv.ai")


def _clean_gemini_schema(schema: dict) -> dict:
    """Recursively strip unsupported 'additionalProperties' from Gemini schema while preserving structure."""
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for key, val in schema.items():
        if key == "additionalProperties":
            continue
        if isinstance(val, dict):
            cleaned[key] = _clean_gemini_schema(val)
        elif isinstance(val, list):
            cleaned[key] = [_clean_gemini_schema(item) if isinstance(item, dict) else item for item in val]
        else:
            cleaned[key] = val
    return cleaned


class AIClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self._cooldowns: dict[tuple[str, str], float] = {}

    def configured(self, provider: str) -> bool:
        if provider in {"Gemini", "Google"}:
            return bool(self.settings.gemini_api_key)
        if provider == "Groq":
            return bool(self.settings.api_key)
        if provider == "Mistral":
            return bool(self.settings.mistral_api_key)
        return False

    def _configuration(self, provider: str):
        cfg = self.settings
        if provider in {"Gemini", "Google"}:
            return cfg.gemini_api_key, cfg.gemini_model, "GEMINI_API_KEY"
        if provider == "Groq":
            return cfg.api_key, cfg.model, "GROQ_API_KEY"
        if provider == "Mistral":
            return cfg.mistral_api_key, cfg.mistral_model, "MISTRAL_API_KEY"
        raise ValueError(f"Unknown AI provider: {provider}")

    def _get_fallback_chain(self) -> list[tuple[str, str, str]]:
        """Configured fallback order:
        1. Google: gemini-3.6-flash
        2. Google: gemini-3.8-flash
        3. Mistral: mistral-small-2603
        """
        cfg = self.settings
        return [
            ("Google", cfg.gemini_model, cfg.gemini_api_key),
            ("Google", cfg.gemini_fallback_model, cfg.gemini_api_key),
            ("Mistral", cfg.mistral_model, cfg.mistral_api_key),
        ]

    def _is_on_cooldown(self, provider: str, model: str) -> bool:
        expires = self._cooldowns.get((provider, model), 0.0)
        return time.monotonic() < expires

    def _set_cooldown(self, provider: str, model: str, duration: float = 300.0):
        self._cooldowns[(provider, model)] = time.monotonic() + duration

    def _clear_cooldown(self, provider: str, model: str):
        self._cooldowns.pop((provider, model), None)

    def _is_quota_exhausted(self, status_code: int, response_text: str) -> bool:
        if status_code != 429:
            return False
        lower = response_text.lower()
        return any(term in lower for term in (
            "quota", "resource_exhausted", "daily limit", "per day",
            "exceeded your current quota", "insufficient_quota", "free tier", "billing"
        ))

    def _interruptible_sleep(self, seconds: float, cancel_event=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            check_cancel(cancel_event)
            step = min(0.05, end - time.monotonic())
            if step > 0:
                time.sleep(step)

    def _adapt_for_mistral(self, system: str, prompt: dict, schema: dict, output_limit: int, max_budget: int = 256000) -> list[dict]:
        """Check input budget for Mistral Small 4 (256k window) and bound chunking preserving document order."""
        sys_tok = estimate_tokens(system)
        sch_tok = estimate_tokens(json.dumps(schema))
        prompt_str = json.dumps(prompt, ensure_ascii=False)
        p_tok = estimate_tokens(prompt_str)
        total = sys_tok + sch_tok + p_tok + output_limit

        effective_limit = min(max_budget, self.settings.token_limit)
        if total <= effective_limit:
            return [prompt]

        if isinstance(prompt, dict) and "sections" in prompt and isinstance(prompt["sections"], list):
            sections_list = prompt["sections"]
            chunk_size = max(1, len(sections_list) // 3)
            chunks = []
            for i in range(0, len(sections_list), chunk_size):
                sub_sec = sections_list[i:i + chunk_size]
                chunk_prompt = dict(prompt)
                chunk_prompt["sections"] = sub_sec
                chunk_prompt["source_omitted"] = True
                chunk_prompt.pop("source_files", None)
                chunks.append(chunk_prompt)
            return chunks

        if isinstance(prompt, dict) and "source_files" in prompt:
            reduced = dict(prompt)
            reduced.pop("source_files", None)
            reduced["source_omitted"] = True
            return [reduced]

        return [prompt]

    def _request_with_fallback(
        self,
        system: str,
        prompt: dict,
        schema: dict,
        usage,
        cancel_event=None,
        progress=None,
        candidate_models: list[tuple[str, str, str]] | None = None,
        reserved_output_tokens: int | None = None,
    ):
        """Unified request flow trying models in order with exponential backoff and deadline enforcement."""
        check_cancel(cancel_event)
        candidates = candidate_models if candidate_models is not None else self._get_fallback_chain()
        deadline = getattr(self.settings, "overall_deadline", 120)
        max_retries = getattr(self.settings, "max_retries", 2)
        start_time = time.monotonic()
        diagnostics = []
        last_error = ""

        mistral_configured = bool(self.settings.mistral_api_key)

        for provider, model, key in candidates:
            check_cancel(cancel_event)
            elapsed = time.monotonic() - start_time
            remaining = deadline - elapsed
            if remaining <= 0:
                raise ProviderError(f"Overall request deadline of {deadline}s exceeded. Last error: {last_error}")

            if not key or not key.strip():
                if provider == "Mistral":
                    diagnostics.append(f"Mistral ({model}): MISTRAL_API_KEY is not configured")
                else:
                    diagnostics.append(f"{provider} ({model}): API key is not configured")
                continue

            if self._is_on_cooldown(provider, model):
                diagnostics.append(f"{provider} ({model}): cooling down due to quota or repeated failures")
                continue

            if progress:
                progress(f"Connecting to {provider} ({model})…")

            output_tokens = reserved_output_tokens or self.settings.max_output_tokens
            prompts_to_try = [prompt]
            if provider == "Mistral":
                prompts_to_try = self._adapt_for_mistral(system, prompt, schema, output_tokens)

            for prompt_item in prompts_to_try:
                for attempt in range(max_retries + 1):
                    check_cancel(cancel_event)
                    elapsed = time.monotonic() - start_time
                    remaining = deadline - elapsed
                    if remaining <= 0:
                        raise ProviderError(f"Overall request deadline of {deadline}s exceeded. Last error: {last_error}")

                    attempt_timeout = min(float(self.settings.ai_timeout), max(1.0, remaining))
                    estimate = estimate_tokens(system + json.dumps(prompt_item, ensure_ascii=False) + json.dumps(schema)) + 256
                    output_limit = usage.authorize(estimate, output_tokens)
                    accounted = False

                    if provider in {"Google", "Gemini"}:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='-')}:generateContent"
                        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
                        cleaned_schema = _clean_gemini_schema(schema)
                        gen_cfg = {
                            "maxOutputTokens": output_limit,
                            "responseMimeType": "application/json",
                            "responseSchema": cleaned_schema,
                            "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": cleaned_schema}},
                        }
                        if model == "gemini-3.5-flash-lite":
                            gen_cfg["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
                        body = {
                            "systemInstruction": {"parts": [{"text": system}]},
                            "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt_item, ensure_ascii=False)}]}],
                            "generationConfig": gen_cfg,
                        }
                    elif provider == "Mistral":
                        url = "https://api.mistral.ai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                        body = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": json.dumps(prompt_item, ensure_ascii=False)},
                            ],
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {"name": "resume_operation", "strict": True, "schema": schema},
                            },
                            "max_tokens": output_limit,
                            "temperature": 0.1,
                        }
                    else:  # Groq
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                        body = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": json.dumps(prompt_item, ensure_ascii=False)},
                            ],
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {"name": "resume_operation", "strict": True, "schema": schema},
                            },
                            "max_completion_tokens": output_limit,
                        }

                    response = None
                    try:
                        with httpx.Client(timeout=attempt_timeout, transport=self.transport, follow_redirects=False) as client:
                            response = client.post(url, headers=headers, json=body)
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
                        failure_cat = "timeout" if isinstance(exc, httpx.TimeoutException) else "connection_error"
                        logger.warning("Provider=%s Model=%s Attempt=%d Elapsed=%.2fs Category=%s",
                                       provider, model, attempt + 1, time.monotonic() - start_time, failure_cat)
                        last_error = f"{provider} {failure_cat}"
                        if attempt < max_retries:
                            delay = (1.0 if attempt == 0 else 2.0) * (0.8 + 0.4 * random.random())
                            if delay < remaining:
                                if progress:
                                    progress(f"{provider} ({model}) {failure_cat}; retrying in {delay:.1f}s…")
                                self._interruptible_sleep(delay, cancel_event)
                                continue
                        diagnostics.append(f"{provider} ({model}): {failure_cat} retries exhausted")
                        break

                    status_code = response.status_code
                    response_text = response.text

                    if status_code == 200:
                        try:
                            data = response.json()
                            metadata = data.get("usageMetadata" if provider in {"Google", "Gemini"} else "usage") or {}
                            total = metadata.get("totalTokenCount" if provider in {"Google", "Gemini"} else "total_tokens")
                            exact = type(total) is int and total >= 0
                            usage.record(total if exact else estimate + output_limit, estimated=not exact)
                            accounted = True

                            check_cancel(cancel_event)

                            if provider in {"Google", "Gemini"}:
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

                            clean_text = content.strip()
                            if clean_text.startswith("```"):
                                clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                                clean_text = re.sub(r"\s*```$", "", clean_text)
                            result = json.loads(clean_text)
                            validate_json(result, schema)
                            self._clear_cooldown(provider, model)
                            logger.info("Provider=%s Model=%s Attempt=%d Elapsed=%.2fs Category=success",
                                        provider, model, attempt + 1, time.monotonic() - start_time)
                            return result
                        except OperationCancelled:
                            raise
                        except Exception as parse_err:
                            failure_cat = "invalid_schema"
                            logger.warning("Provider=%s Model=%s Attempt=%d Elapsed=%.2fs Category=%s",
                                           provider, model, attempt + 1, time.monotonic() - start_time, failure_cat)
                            last_error = f"{provider} {failure_cat}"
                            diagnostics.append(f"{provider} ({model}): returned invalid response format")
                            break
                        finally:
                            if not accounted:
                                usage.record(estimate + output_limit, estimated=True)

                    elif status_code == 429:
                        if self._is_quota_exhausted(status_code, response_text):
                            logger.warning("Provider=%s Model=%s Attempt=%d Category=quota_exhausted", provider, model, attempt + 1)
                            self._set_cooldown(provider, model, duration=300.0)
                            diagnostics.append(f"{provider} ({model}): daily quota exhausted (429)")
                            if progress:
                                progress(f"{provider} ({model}) daily quota exhausted; switching to next model…")
                            break
                        else:
                            retry_after_str = response.headers.get("Retry-After")
                            retry_after = int(retry_after_str) if (retry_after_str and retry_after_str.isdigit()) else 0
                            if retry_after > 0 and retry_after <= 10 and retry_after < remaining:
                                if progress:
                                    progress(f"{provider} ({model}) rate limit; waiting {retry_after}s…")
                                self._interruptible_sleep(float(retry_after) + random.uniform(0.1, 0.4), cancel_event)
                                continue
                            diagnostics.append(f"{provider} ({model}): rate limit exceeded (429)")
                            break

                    elif status_code in {500, 502, 503, 504}:
                        failure_cat = f"server_error_{status_code}"
                        logger.warning("Provider=%s Model=%s Attempt=%d Category=%s", provider, model, attempt + 1, failure_cat)
                        last_error = f"{provider} server error {status_code}"
                        if attempt < max_retries:
                            delay = (1.0 if attempt == 0 else 2.0) * (0.8 + 0.4 * random.random())
                            if delay < remaining:
                                if progress:
                                    progress(f"{provider} ({model}) server error {status_code}; retrying in {delay:.1f}s…")
                                self._interruptible_sleep(delay, cancel_event)
                                continue
                        diagnostics.append(f"{provider} ({model}): server error {status_code} retries exhausted")
                        break

                    elif status_code in {401, 403}:
                        failure_cat = f"auth_error_{status_code}"
                        logger.warning("Provider=%s Model=%s Category=%s", provider, model, failure_cat)
                        diagnostics.append(f"{provider} ({model}): authentication failed ({status_code})")
                        break

                    elif status_code == 400:
                        failure_cat = "bad_request_400"
                        logger.warning("Provider=%s Model=%s Category=%s", provider, model, failure_cat)
                        diagnostics.append(f"{provider} ({model}): request rejected (400)")
                        break

                    else:
                        failure_cat = f"http_{status_code}"
                        diagnostics.append(f"{provider} ({model}): HTTP {status_code}")
                        break

        if not mistral_configured:
            diagnostics.append("Mistral fallback is unavailable because MISTRAL_API_KEY is not configured")
        err_msg = "All configured AI models failed. " + "; ".join(diagnostics)
        raise ProviderError(err_msg)

    def _request(self, provider, system, prompt, schema, usage, cancel_event=None):
        """Single-provider request interface without model fallback."""
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
            if provider in {"Google", "Gemini"}:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='-')}:generateContent"
                headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
                cleaned_schema = _clean_gemini_schema(schema)
                generation = {
                    "maxOutputTokens": output_limit,
                    "responseMimeType": "application/json",
                    "responseSchema": cleaned_schema,
                    "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": cleaned_schema}},
                }
                if model == "gemini-3.5-flash-lite":
                    generation["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
                body = {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
                    "generationConfig": generation,
                }
            else:
                url = ("https://api.groq.com/openai/v1/chat/completions" if provider == "Groq"
                       else "https://api.mistral.ai/v1/chat/completions")
                headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "resume_operation", "strict": True, "schema": schema},
                    },
                    ("max_completion_tokens" if provider == "Groq" else "max_tokens"): output_limit,
                }
                if provider == "Mistral":
                    body["temperature"] = 0.1

            with httpx.Client(timeout=min(float(self.settings.ai_timeout), 120.0),
                              transport=self.transport, follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=body)

            data = None
            if response.status_code == 200:
                try:
                    data = response.json()
                    metadata = data.get("usageMetadata" if provider in {"Google", "Gemini"} else "usage") or {}
                    total = metadata.get("totalTokenCount" if provider in {"Google", "Gemini"} else "total_tokens")
                    exact = type(total) is int and total >= 0
                    usage.record(total if exact else estimate + output_limit, estimated=not exact)
                    accounted = True
                except (ValueError, TypeError, AttributeError):
                    pass

            check_cancel(cancel_event)

            if response.status_code != 200:
                reason = {
                    401: "rejected the API key", 403: "denied access to the model",
                    429: "reached a rate limit or quota", 400: "rejected the model or request format",
                    404: "could not find the configured model",
                }.get(response.status_code, "is unavailable")
                raise ProviderError(f"{provider} {reason}. Check configuration or retry later.")

            try:
                if data is None:
                    raise ValueError("Unreadable provider response")
                if provider in {"Google", "Gemini"}:
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

                clean_text = content.strip()
                if clean_text.startswith("```"):
                    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                    clean_text = re.sub(r"\s*```$", "", clean_text)
                result = json.loads(clean_text)
                validate_json(result, schema)
                return result
            except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                raise ProviderError(f"{provider} returned an incomplete or invalid response.") from None
        except httpx.TimeoutException:
            raise ProviderError(f"{provider} timed out. Your approved source is unchanged.") from None
        except httpx.HTTPError:
            raise ProviderError(f"Could not connect to {provider}. Check your connection and configuration.") from None
        finally:
            if not accounted:
                usage.record(estimate + output_limit, estimated=True)

    def analyze(self, instruction, project, usage, selected_section=None, cancel_event=None, progress=None):
        """Analyze resume and identify target section. Bypasses AI if section is explicitly selected."""
        available = sections(project)
        if not available:
            return {
                "status": "unsupported",
                "section_id": "",
                "question": "No safely bounded sections were found in this template.",
                "proposals": [],
            }
        valid_ids = {item.id for item in available}

        # Requirement 5: Explicit section selection bypasses AI section detection directly
        if selected_section:
            if selected_section not in valid_ids:
                raise ProviderError("Choose a section from the current resume.")
            return {
                "status": "ready",
                "section_id": selected_section,
                "question": "",
                "proposals": [],
            }

        # Automatic detection using configured fallback chain
        source = text_sources(project)
        context = {
            "instruction": instruction,
            "selected_section": None,
            "main_file": project.main_file,
            "sections": [
                {"id": s.id, "title": s.title, "file": s.file, "preview": s.content[:280]}
                for s in available
            ],
        }
        if estimate_tokens(json.dumps(source, ensure_ascii=False)) <= self.settings.full_context_tokens:
            context["source_files"] = source
        else:
            context["source_omitted"] = True

        result = self._request_with_fallback(
            ANALYSIS_PROMPT, context, ANALYSIS_SCHEMA, usage,
            cancel_event=cancel_event, progress=progress,
        )

        if result["status"] == "ready":
            if result["section_id"] not in valid_ids or result["proposals"] or result["question"].strip():
                raise ProviderError("The model did not identify one valid section. Please clarify the target.")
        elif result["status"] == "split":
            if not 2 <= len(result["proposals"]) <= 20 or any(
                p["section_id"] not in valid_ids or not p["instruction"].strip() for p in result["proposals"]
            ):
                raise ProviderError("The model could not safely split the request. Ask for one section at a time.")
        elif not result["question"].strip():
            raise ProviderError("The model returned no clarification or limitation explanation.")
        return result

    def rewrite(self, instruction, section, usage, cancel_event=None, progress=None):
        """Rewrite section LaTeX using Groq (if configured) or the fallback chain."""
        prompt_data = {
            "instruction": instruction,
            "section_title": section.title,
            "section_body": section.content,
        }
        candidates = []
        if self.settings.api_key:
            candidates.append(("Groq", self.settings.model, self.settings.api_key))
        candidates.extend(self._get_fallback_chain())

        response = self._request_with_fallback(
            EDIT_PROMPT, prompt_data, EDIT_SCHEMA, usage,
            cancel_event=cancel_event, progress=progress,
            candidate_models=candidates,
        )
        if response["status"] == "ready":
            if not response["text"].strip() or response["question"].strip():
                raise ProviderError("The model did not return a valid section body.")
            text = response["text"]
            if "\n" not in text and r"\n" in text:
                text = text.replace(r"\r\n", "\n").replace(r"\n", "\n")
            response["text"] = re.sub(r"\\\\([A-Za-z@]+)", r"\\\1", text)
        elif response["text"].strip() or not response["question"].strip():
            raise ProviderError("The model did not return a valid clarification.")
        return EditResult(**response)

    def repair(self, provider, project, approved, logs, usage, cancel_event=None, failed_attempts=None, progress=None):
        """Repair LaTeX compilation errors with specified provider or fallback chain."""
        if provider not in {"Groq", "Mistral", "Google", "Gemini"}:
            raise ValueError("Repair supports Groq and Mistral only.")
        context = repair_context(project, approved, logs, self.settings.full_context_tokens, failed_attempts)
        return self._request(provider, REPAIR_PROMPT, context, REPAIR_SCHEMA, usage, cancel_event)["patches"]
