from __future__ import annotations

import json
from enum import StrEnum


class Provider(StrEnum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
    OPENCLAW = "openclaw"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


OPENAI_LIKE_PROVIDERS = {
    Provider.OPENAI,
    Provider.OPENAI_COMPATIBLE,
    Provider.OPENCLAW,
    Provider.GOOGLE,
}


def resolve_provider(name: str | None) -> Provider:
    if not name:
        return Provider.OPENAI
    normalized = name.strip().lower()
    for provider in Provider:
        if provider.value == normalized:
            return provider
    if normalized in {"openai_compatible", "openai-compatible", "openai-compatible-api"}:
        return Provider.OPENAI_COMPATIBLE
    raise ValueError(f"Unsupported upstream provider: {name}")


def normalize_request(provider: Provider, path: str, body: dict) -> tuple[str, dict]:
    payload = dict(body)
    if provider in OPENAI_LIKE_PROVIDERS:
        return "/v1/chat/completions", payload

    system_messages: list[str] = []
    conversational: list[dict] = []
    for message in payload.get("messages", []):
        if message.get("role") == "system":
            system_messages.append(str(message.get("content", "")))
            continue
        conversational.append(message)
    normalized = {
        "model": payload.get("model", "claude-3-5-haiku-latest"),
        "messages": conversational,
        "stream": payload.get("stream", False),
        "max_tokens": payload.get("max_tokens", 1024),
    }
    if system_messages:
        normalized["system"] = "\n\n".join(system_messages)
    return "/v1/messages", normalized


def extract_text_from_json(provider: Provider, payload: dict) -> str:
    if provider in OPENAI_LIKE_PROVIDERS:
        choices = payload.get("choices", [])
        if not choices:
            return ""
        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "".join(parts)
        return str(content)

    content = payload.get("content", [])
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def extract_stream_text(provider: Provider, chunk_text: str) -> str:
    text_parts: list[str] = []
    for line in chunk_text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        raw = line[6:].strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if provider in OPENAI_LIKE_PROVIDERS:
            choices = data.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            if isinstance(content, list):
                text_parts.extend(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            else:
                text_parts.append(str(content))
            continue

        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            text_parts.append(str(delta.get("text", "")))
        elif data.get("type") == "message_delta":
            delta = data.get("delta", {})
            if isinstance(delta.get("text"), str):
                text_parts.append(delta["text"])
    return "".join(text_parts)
