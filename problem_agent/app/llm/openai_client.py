from __future__ import annotations

import hashlib
import json
from typing import Any

from app.config import Settings, get_settings


class LLMServiceError(RuntimeError):
    """Raised when an LLM call cannot complete safely."""


class LLMOutputValidationError(LLMServiceError):
    """Raised when an LLM response does not match the expected schema."""


class OpenAIClient:
    """Small wrapper around provider-backed structured JSON generation.

    Tests and local development can opt into deterministic agent fallbacks.
    Production should set the selected provider API key and keep fallbacks disabled.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.last_usage: dict[str, Any] | None = None
        self.last_request_id: str | None = None
        self.last_model: str | None = None

    def reset_last_call(self) -> None:
        self.last_usage = None
        self.last_request_id = None
        self.last_model = None

    @property
    def available(self) -> bool:
        if self._provider() == "gemini":
            return bool(self.settings.gemini_api_key)
        return bool(self.settings.openai_api_key)

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        image_inputs: list[dict[str, Any]] | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        prompt_cache_key: str | None = None,
        safety_identifier: str | None = None,
    ) -> dict:
        self.reset_last_call()
        self.last_model = model
        provider = self._provider()
        if provider == "gemini":
            return self._generate_json_with_gemini(
                model=model,
                prompt=prompt,
                schema_name=schema_name,
                schema=schema,
                image_inputs=image_inputs,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
            )
        if provider != "openai":
            raise LLMServiceError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
        return self._generate_json_with_openai(
            model=model,
            prompt=prompt,
            schema_name=schema_name,
            schema=schema,
            image_inputs=image_inputs,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            prompt_cache_key=prompt_cache_key,
            safety_identifier=safety_identifier,
        )

    def _provider(self) -> str:
        return str(self.settings.llm_provider or "openai").strip().lower()

    def _generate_json_with_openai(
        self,
        *,
        model: str,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        image_inputs: list[dict[str, Any]] | None,
        max_output_tokens: int | None,
        reasoning_effort: str | None,
        prompt_cache_key: str | None,
        safety_identifier: str | None,
    ) -> dict:
        if not self.settings.openai_api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured")

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
                max_retries=self.settings.openai_max_retries,
            )
            request_payload: dict[str, Any] = {
                "model": model,
                "input": self._response_input(prompt=prompt, image_inputs=image_inputs),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
            if max_output_tokens is not None:
                request_payload["max_output_tokens"] = max_output_tokens
            if reasoning_effort:
                request_payload["reasoning"] = {"effort": reasoning_effort}
            if prompt_cache_key:
                request_payload["prompt_cache_key"] = prompt_cache_key
            if safety_identifier:
                request_payload["safety_identifier"] = safety_identifier

            response = client.responses.create(**request_payload)
            self.last_usage = self._usage_to_dict(getattr(response, "usage", None))
            self.last_request_id = getattr(response, "id", None)
            text = getattr(response, "output_text", None)
            if not text:
                raise LLMServiceError("OpenAI response did not include output_text")
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMOutputValidationError(f"OpenAI response was not valid JSON: {exc}") from exc
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(f"OpenAI structured output request failed: {exc}") from exc

    def _generate_json_with_gemini(
        self,
        *,
        model: str,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        image_inputs: list[dict[str, Any]] | None,
        max_output_tokens: int | None,
        reasoning_effort: str | None,
    ) -> dict:
        if not self.settings.gemini_api_key:
            raise LLMServiceError("GEMINI_API_KEY is not configured")

        try:
            import httpx

            generation_config: dict[str, Any] = {
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": self._gemini_json_schema(schema),
                    }
                },
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            }
            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = max_output_tokens

            request_payload: dict[str, Any] = {
                "contents": [{"role": "user", "parts": self._gemini_parts(prompt=prompt, image_inputs=image_inputs)}],
                "generationConfig": generation_config,
            }
            url = f"{self._gemini_native_base_url()}/models/{model}:generateContent"
            with httpx.Client(timeout=self.settings.openai_timeout_seconds) as client:
                response = client.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.settings.gemini_api_key,
                    },
                    json=request_payload,
                )
            self.last_request_id = response.headers.get("x-request-id")
            response_payload = response.json()
            if response.status_code >= 400:
                error = response_payload.get("error", response_payload)
                raise LLMServiceError(f"Gemini structured output request failed: {error}")
            self.last_usage = self._gemini_usage_to_dict(response_payload.get("usageMetadata"))
            finish_reason = self._gemini_finish_reason(response_payload)
            text = self._gemini_response_text(response_payload)
            if not text:
                raise LLMServiceError("Gemini response did not include text content")
            return self._loads_gemini_json(text, finish_reason=finish_reason)
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(f"Gemini structured output request failed: {exc}") from exc

    def _loads_gemini_json(self, text: str, *, finish_reason: str | None = None) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError as original_exc:
            repaired = self._escape_json_string_control_chars(text)
            if repaired != text:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError as repaired_exc:
                    raise LLMOutputValidationError(
                        "Gemini response was not valid JSON after repair: "
                        f"{repaired_exc}; finish_reason={finish_reason}; len={len(text)}"
                    ) from repaired_exc
            raise LLMOutputValidationError(
                f"Gemini response was not valid JSON: {original_exc}; "
                f"finish_reason={finish_reason}; len={len(text)}"
            ) from original_exc

    def _escape_json_string_control_chars(self, text: str) -> str:
        output: list[str] = []
        in_string = False
        escaped = False
        for char in text:
            if not in_string:
                output.append(char)
                if char == '"':
                    in_string = True
                continue

            if escaped:
                output.append(char)
                escaped = False
            elif char == "\\":
                output.append(char)
                escaped = True
            elif char == '"':
                output.append(char)
                in_string = False
            elif char == "\n":
                output.append("\\n")
            elif char == "\r":
                output.append("\\r")
            elif char == "\t":
                output.append("\\t")
            else:
                output.append(char)
        return "".join(output)

    def _gemini_native_base_url(self) -> str:
        base_url = str(self.settings.gemini_openai_base_url).rstrip("/")
        if base_url.endswith("/openai"):
            return base_url[: -len("/openai")]
        return base_url

    def _gemini_parts(self, *, prompt: str, image_inputs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for index, image_input in enumerate(image_inputs or [], start=1):
            image_payload = str(image_input.get("image") or "").strip()
            if not image_payload:
                continue
            label = str(image_input.get("label") or f"visual_source_{index}").strip()
            chunk_id = str(image_input.get("chunk_id") or "").strip()
            page = image_input.get("page")
            note_parts = [f"[visual_source {index}: {label}"]
            if chunk_id:
                note_parts.append(f"chunk_id={chunk_id}")
            if page is not None:
                note_parts.append(f"page={page}")
            parts.append({"text": " ".join(note_parts) + "]"})
            mime_type, data = self._gemini_inline_image(image_payload)
            parts.append({"inline_data": {"mime_type": mime_type, "data": data}})
        return parts

    def _gemini_inline_image(self, image_payload: str) -> tuple[str, str]:
        if image_payload.startswith("data:") and "," in image_payload:
            metadata, data = image_payload.split(",", 1)
            mime_type = metadata[5:].split(";", 1)[0] or "image/png"
            return mime_type, data
        return "image/png", image_payload

    def _gemini_response_text(self, response_payload: dict[str, Any]) -> str | None:
        candidates = response_payload.get("candidates") or []
        if not candidates:
            return None
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        text_parts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
        return "".join(text_parts) if text_parts else None

    def _gemini_finish_reason(self, response_payload: dict[str, Any]) -> str | None:
        candidates = response_payload.get("candidates") or []
        if not candidates:
            return None
        return candidates[0].get("finishReason")

    def _gemini_usage_to_dict(self, usage: Any) -> dict[str, Any] | None:
        if not isinstance(usage, dict):
            return None
        return {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        }

    def _gemini_json_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "type",
            "properties",
            "required",
            "additionalProperties",
            "enum",
            "format",
            "items",
            "prefixItems",
            "minItems",
            "maxItems",
            "minimum",
            "maximum",
            "title",
            "description",
        }

        def sanitize(value: Any) -> Any:
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if not isinstance(value, dict):
                return value

            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if key == "exclusiveMinimum" and isinstance(item, (int, float)):
                    sanitized["minimum"] = item
                    continue
                if key not in allowed_keys:
                    continue
                if key == "properties" and isinstance(item, dict):
                    sanitized[key] = {property_name: sanitize(property_schema) for property_name, property_schema in item.items()}
                    continue
                if key == "additionalProperties" and isinstance(item, bool):
                    sanitized[key] = item
                    continue
                sanitized[key] = sanitize(item)
            return sanitized

        return sanitize(schema)

    def _usage_to_dict(self, usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if isinstance(usage, dict):
            return usage
        return {
            key: getattr(usage, key)
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if hasattr(usage, key)
        }

    def _response_input(self, *, prompt: str, image_inputs: list[dict[str, Any]] | None) -> str | list[dict[str, Any]]:
        if not image_inputs:
            return prompt

        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for index, image_input in enumerate(image_inputs, start=1):
            label = str(image_input.get("label") or f"visual_source_{index}").strip()
            chunk_id = str(image_input.get("chunk_id") or "").strip()
            page = image_input.get("page")
            image_payload = str(image_input.get("image") or "").strip()
            if not image_payload:
                continue
            note_parts = [f"[visual_source {index}: {label}"]
            if chunk_id:
                note_parts.append(f"chunk_id={chunk_id}")
            if page is not None:
                note_parts.append(f"page={page}")
            note = " ".join(note_parts) + "]"
            image_item: dict[str, Any] = {
                "type": "input_image",
                "image_url": self._image_data_url(image_payload),
            }
            detail = str(image_input.get("detail") or "").strip()
            if detail in {"low", "high", "auto"}:
                image_item["detail"] = detail
            content.append({"type": "input_text", "text": note})
            content.append(image_item)

        if len(content) == 1:
            return prompt
        return [{"role": "user", "content": content}]

    def _chat_messages(self, *, prompt: str, image_inputs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not image_inputs:
            return [{"role": "user", "content": prompt}]

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for index, image_input in enumerate(image_inputs, start=1):
            label = str(image_input.get("label") or f"visual_source_{index}").strip()
            chunk_id = str(image_input.get("chunk_id") or "").strip()
            page = image_input.get("page")
            image_payload = str(image_input.get("image") or "").strip()
            if not image_payload:
                continue
            note_parts = [f"[visual_source {index}: {label}"]
            if chunk_id:
                note_parts.append(f"chunk_id={chunk_id}")
            if page is not None:
                note_parts.append(f"page={page}")
            content.append({"type": "text", "text": " ".join(note_parts) + "]"})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_data_url(image_payload)},
                }
            )

        if len(content) == 1:
            return [{"role": "user", "content": prompt}]
        return [{"role": "user", "content": content}]

    def _image_data_url(self, image_payload: str) -> str:
        if image_payload.startswith(("data:", "http://", "https://")):
            return image_payload
        return f"data:image/png;base64,{image_payload}"


def safety_identifier_for_user(user_id: str) -> str:
    """Return a stable non-PII identifier for OpenAI safety monitoring."""

    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"user_{digest[:32]}"
