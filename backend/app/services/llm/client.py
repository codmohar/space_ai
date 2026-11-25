"""Provider-agnostic LLMClient interface with Gemini default and Pydantic JSON validation."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    model_name: str

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_cls: Type[T],
        max_retries: int = 2,
    ) -> T:
        """Generate structured output validated against schema_cls."""


class GeminiLLMClient(LLMClient):
    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_cls: Type[T],
        max_retries: int = 2,
    ) -> T:
        if not self.api_key:
            raise ApiError(
                "LLM_NOT_CONFIGURED",
                "GEMINI_API_KEY is not configured in environment.",
                status_code=503,
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        last_error: Exception | None = None
        prompt = user_prompt
        fallback_models = list(
            dict.fromkeys(
                m
                for m in (
                    self.model_name,
                    "gemini-flash-latest",
                    "gemini-2.5-flash-lite",
                    "gemini-2.0-flash",
                )
                if m
            )
        )
        active_model_idx = 0
        total_attempts = max(max_retries + 1, len(fallback_models))

        for attempt in range(total_attempts):
            current_model = fallback_models[min(active_model_idx, len(fallback_models) - 1)]
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=schema_cls,
                    ),
                )
                raw_text = (response.text or "").strip()
                if not raw_text:
                    raise ValueError("Empty response from Gemini")
                parsed = json.loads(raw_text)
                return schema_cls.model_validate(parsed)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("Structured LLM attempt %d failed validation: %s", attempt + 1, exc)
                prompt = (
                    f"{user_prompt}\n\n"
                    f"[FORMAT REPAIR] Your previous output failed schema validation ({exc}). "
                    "Return valid JSON strictly matching the schema."
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.error("Gemini API error (%s) on attempt %d: %s", current_model, attempt + 1, exc)
                if active_model_idx + 1 < len(fallback_models):
                    active_model_idx += 1
                if attempt + 1 < total_attempts:
                    time.sleep(min(2.0, 0.6 * (attempt + 1)))

        raise ApiError(
            "LLM_GENERATION_FAILED",
            f"Structured generation failed after retries: {last_error}",
            status_code=502,
        )


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider.lower() == "gemini":
        return GeminiLLMClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )
    raise ApiError(
        "UNSUPPORTED_LLM_PROVIDER",
        f"Unsupported LLM_PROVIDER: {settings.llm_provider}",
        status_code=500,
    )
