"""Google Gemini implementation of LLMClient (tool calling / function calling).

Useful as a free-tier alternative to Claude for testing the pipeline end to end — get a key with
no billing setup at https://aistudio.google.com/apikey.
"""
from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from codeforge.llm.base import LLMClient, LLMResponse, ToolCall

# Pydantic's model_json_schema() emits metadata Gemini's schema parser doesn't need/accept;
# stripping it keeps the schema to the subset Gemini actually validates against.
_UNSUPPORTED_SCHEMA_KEYS = {"title", "additionalProperties", "$schema"}


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    cleaned = {k: v for k, v in schema.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(cleaned.get("properties"), dict):
        cleaned["properties"] = {
            name: _clean_schema(prop) if isinstance(prop, dict) else prop
            for name, prop in cleaned["properties"].items()
        }
    if isinstance(cleaned.get("items"), dict):
        cleaned["items"] = _clean_schema(cleaned["items"])
    return cleaned


class GeminiClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set (check your .env)")
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=max_retries),
            ),
        )
        self._model = model

    def create_message(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]

        function_declarations = [
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters_json_schema=_clean_schema(tool["input_schema"]),
            )
            for tool in (tools or [])
        ]
        gemini_tools = (
            [types.Tool(function_declarations=function_declarations)] if function_declarations else None
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                tools=gemini_tools,
            ),
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        candidate = response.candidates[0] if response.candidates else None
        parts = candidate.content.parts if candidate and candidate.content else None
        for part in parts or []:
            if part.text:
                text_parts.append(part.text)
            if part.function_call:
                tool_calls.append(
                    ToolCall(
                        id=part.function_call.id or part.function_call.name,
                        name=part.function_call.name,
                        input=part.function_call.args or {},
                    )
                )

        stop_reason = None
        if candidate is not None and candidate.finish_reason is not None:
            stop_reason = getattr(candidate.finish_reason, "value", None) or str(candidate.finish_reason)

        return LLMResponse(
            text="".join(text_parts), tool_calls=tool_calls, stop_reason=stop_reason, raw=response
        )
