from __future__ import annotations

import asyncio
import os
import re

from aiohttp import ClientSession, ClientTimeout

from session_sift.config import SessionSiftConfig
from session_sift.providers import Provider, extract_text_from_json, resolve_provider
from session_sift.utils import safe_str


FLUFF_PATTERNS = [
    (re.compile(r"(great|sounds good|sure|okay|understood|got it|will do)", re.IGNORECASE), 0.8),
    (re.compile(r"i (have|will|am going to|shall) (now |)(look|check|analyze|read)", re.IGNORECASE), 0.6),
    (re.compile(r"^(yes|no|ok|done|complete|finished)\.?$", re.IGNORECASE | re.MULTILINE), 0.9),
    (re.compile(r"let me (now |)(explain|walk you through|show you)", re.IGNORECASE), 0.4),
]

FILE_SIGNAL = re.compile(r"(?:\.{0,2}/|[A-Za-z]:/)[^\s]+")
NUMBER_SIGNAL = re.compile(r"\b\d+(?:\.\d+)?\b")
ERROR_SIGNAL = re.compile(r"[A-Za-z_]+(?:Error|Exception)|Traceback|FAILED")

SYSTEM_PROMPT = """You are a context compressor for an AI agent session.
Your task: compress the provided conversation turns into a dense summary.

Rules:
1. Preserve all file paths, function names, variable names, and error messages VERBATIM.
2. Preserve all numerical values, timestamps, and configuration values VERBATIM.
3. Discard: greetings, acknowledgments, redundant explanations, status updates.
4. Output ONLY the compressed summary. No preamble. No explanation.
5. Target: 30% of original token count.
6. Format: [SESSION SIFT SUMMARY - turns N-M]: <compressed content>
"""


def fluff_score(text: str) -> float:
    if not text or len(text) < 20:
        return 1.0
    score = 0.0
    for pattern, weight in FLUFF_PATTERNS:
        matches = len(pattern.findall(text))
        score += weight * min(matches, 3)
    return min(score / 3.0, 1.0)


class SemanticCompressor:
    def __init__(self, config: SessionSiftConfig) -> None:
        self.config = config

    async def run(self, messages: list[dict]) -> tuple[list[dict], int]:
        try:
            async with asyncio.timeout(self.config.pass3_timeout_secs):
                return await self._compress(messages)
        except (asyncio.TimeoutError, Exception):
            return messages, 0

    async def _compress(self, messages: list[dict]) -> tuple[list[dict], int]:
        candidates = [message for message in messages if self._is_candidate(message)]
        if candidates:
            remote_result = await self._compress_with_model(candidates)
            if remote_result is not None:
                return self._apply_remote_summary(messages, candidates, remote_result)
        savings = 0
        result: list[dict] = []
        for message in messages:
            if not self._is_candidate(message):
                result.append(message)
                continue
            content = safe_str(message.get("content", ""))
            summary = self._summarize_text(content, message["_session_sift"].get("turn", 0))
            if summary == content:
                result.append(message)
                continue
            updated = message.copy()
            updated["content"] = summary
            savings += max(0, (len(content) - len(summary)) // 4)
            result.append(updated)
        return result, savings

    def _is_candidate(self, message: dict) -> bool:
        if message["_session_sift"].get("protected"):
            return False
        content = safe_str(message.get("content", ""))
        return (
            message["_session_sift"].get("retention_weight", 1.0)
            < self.config.pruning_threshold
            or fluff_score(content) >= 0.55
        )

    async def _compress_with_model(self, messages: list[dict]) -> str | None:
        api_key = os.getenv(self.config.pass3_api_key_env)
        if not api_key:
            return None
        provider = resolve_provider(self.config.pass3_provider)
        turns = [message["_session_sift"].get("turn_index", message["_session_sift"].get("turn", 0)) for message in messages]
        batch_text = "\n---\n".join(
            f"[turn {message['_session_sift'].get('turn_index', message['_session_sift'].get('turn', 0))}] "
            f"{message.get('role', 'user')}: {safe_str(message.get('content', ''))}"
            for message in messages
        )
        timeout = ClientTimeout(total=self.config.pass3_timeout_secs)
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        if provider in {Provider.OPENAI, Provider.OPENAI_COMPATIBLE, Provider.OPENCLAW, Provider.GOOGLE}:
            headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            payload = {
                "model": self.config.pass3_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": batch_text},
                ],
                "stream": False,
                "max_tokens": 1024,
            }
            path = "/v1/chat/completions"
        else:
            payload = {
                "model": self.config.pass3_model,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": batch_text}],
                "max_tokens": 1024,
            }
            path = "/v1/messages"
        async with ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.config.pass3_base_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    return None
                payload_json = await response.json()
        summary = extract_text_from_json(provider, payload_json).strip()
        if not summary:
            return None
        return summary.replace("turns N-M", f"turns {min(turns)}-{max(turns)}")

    def _apply_remote_summary(
        self, messages: list[dict], candidates: list[dict], summary: str
    ) -> tuple[list[dict], int]:
        savings = 0
        first_index = candidates[0]["_session_sift"]["index"]
        last_index = candidates[-1]["_session_sift"]["index"]
        result: list[dict] = []
        emitted = False
        original_chars = sum(len(safe_str(message.get("content", ""))) for message in candidates)
        for message in messages:
            index = message["_session_sift"]["index"]
            if first_index <= index <= last_index and self._is_candidate(message):
                if not emitted:
                    updated = candidates[0].copy()
                    updated["content"] = summary
                    result.append(updated)
                    emitted = True
                    savings += max(0, (original_chars - len(summary)) // 4)
                continue
            result.append(message)
        return result, savings

    def _summarize_text(self, text: str, turn: int) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        tokens: list[str] = []
        for line in lines:
            tokens.extend(FILE_SIGNAL.findall(line))
            tokens.extend(ERROR_SIGNAL.findall(line))
            tokens.extend(NUMBER_SIGNAL.findall(line))
        if not tokens:
            tokens = lines[:2]
        snippet = " | ".join(dict.fromkeys(tokens))
        if not snippet:
            return text
        return f"[SESSION SIFT SUMMARY - turns {turn}-{turn}]: {snippet}"
