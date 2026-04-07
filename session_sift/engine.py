from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from session_sift.config import SessionSiftConfig
from session_sift.models import SavingsReport
from session_sift.passes.pass1 import StructuralPruner
from session_sift.passes.pass2 import TemporalPruner
from session_sift.passes.pass3 import SemanticCompressor
from session_sift.registry import FileRegistry
from session_sift.utils import count_tokens, safe_str


FILE_SIGNAL = __import__("re").compile(r"(?:\.{0,2}/|[A-Za-z]:/)[^\s]+")
NUMBER_SIGNAL = __import__("re").compile(r"\b\d+(?:\.\d+)?\b")
CODE_SIGNAL = __import__("re").compile(r"\b(?:def|class|async\s+def)\b")
ERROR_SIGNAL = __import__("re").compile(r"[A-Za-z_]+(?:Error|Exception)|Traceback|FAILED")


class SessionSiftEngine:
    def __init__(self, config: SessionSiftConfig | None = None) -> None:
        self.config = config or SessionSiftConfig()
        session_id = uuid4().hex
        self._registry = FileRegistry(self.config.registry_path, session_id=session_id)
        self._pass1 = StructuralPruner(self.config)
        self._pass2 = TemporalPruner(self.config, self._registry)
        self._pass3 = SemanticCompressor(self.config)
        self._lock = asyncio.Lock()
        self._turn_counter = 0
        self._history: list[dict] = []
        self._last_annotated: list[dict] = []
        self._total_savings = 0
        self._last_report: SavingsReport | None = None

    async def refine(
        self, messages: list[dict], force_pass3: bool = False
    ) -> tuple[list[dict], SavingsReport]:
        start = time.monotonic()
        original_tokens = count_tokens(messages)
        async with self._lock:
            self._turn_counter += 1
            turn = self._turn_counter

        if len(messages) < 10:
            report = SavingsReport(
                original_tokens=original_tokens,
                refined_tokens=original_tokens,
                pass1_savings=0,
                pass2_savings=0,
                pass3_savings=0,
                elapsed_ms=0.0,
                turn=turn,
            )
            return messages, report

        annotated = self._annotate(messages, turn)
        self._last_annotated = annotated
        pass1_out, pass1_savings = self._pass1.run(annotated)
        self._attach_retention_weights(pass1_out)
        try:
            pass2_out, pass2_savings = await self._pass2.run(pass1_out)
        except Exception:
            pass2_out, pass2_savings = pass1_out, 0
        pass3_out, pass3_savings = pass2_out, 0
        if force_pass3 or self._needs_pass3(pass2_out):
            pass3_out, pass3_savings = await self._pass3.run(pass2_out)

        refined = self._strip_metadata(pass3_out)
        elapsed_ms = (time.monotonic() - start) * 1000
        report = SavingsReport(
            original_tokens=original_tokens,
            refined_tokens=count_tokens(refined),
            pass1_savings=pass1_savings,
            pass2_savings=pass2_savings,
            pass3_savings=pass3_savings,
            elapsed_ms=elapsed_ms,
            turn=turn,
            session_id=self._registry.session_id,
        )
        self._total_savings += report.total_savings
        self._last_report = report
        return refined, report

    def status(self) -> dict:
        payload = {
            "turn_count": self._turn_counter,
            "session_id": self._registry.session_id,
            "registry_path": self.config.registry_path,
            "total_savings_tokens": self._total_savings,
            "history_entries": len(self._history),
        }
        if self._last_report is not None:
            payload["last_report"] = self._last_report.to_dict()
        return payload

    async def append_turn(self, message: dict) -> None:
        async with self._lock:
            self._history.append(message)

    async def import_dna(self, input_path: str) -> dict:
        return await self._registry.import_dna(input_path)

    async def export_dna(self, output_path: str | None = None) -> dict:
        return await self._registry.export_dna_with_context(
            output_path or self.config.dna_path,
            total_turns=self._turn_counter,
            total_tokens_saved=self._total_savings,
            recent_messages=self._last_annotated or self._history,
        )

    def _needs_pass3(self, messages: list[dict]) -> bool:
        if not self.config.pass3_enabled:
            return False
        remaining = count_tokens(messages)
        return remaining > (self.config.max_context_tokens * 0.70) or any(
            message.get("_session_sift", {}).get("retention_weight", 1.0)
            < self.config.pruning_threshold
            for message in messages
        )

    def _annotate(self, messages: list[dict], turn: int) -> list[dict]:
        result: list[dict] = []
        total = len(messages)
        for index, message in enumerate(messages):
            updated = message.copy()
            age = max(0, total - 1 - index)
            recent = age < self.config.recency_window
            updated["_session_sift"] = {
                "turn": turn,
                "index": index,
                "age": age,
                "turn_index": max(1, turn - age),
                "protected": (
                    message.get("role") == "system"
                    or recent
                    or self._is_protected(message.get("content", ""))
                ),
            }
            result.append(updated)
        return result

    def _attach_retention_weights(self, messages: list[dict]) -> None:
        for message in messages:
            structure = self._structural_score(message)
            age = message["_session_sift"].get("age", 0)
            decay = 2.718281828 ** (-self.config.decay_lambda * age)
            recent = age < self.config.recency_window
            recency_boost = 1.0 + self.config.decay_recency_boost if recent else 1.0
            protection = 10.0 if message["_session_sift"].get("protected") else 1.0
            weight = structure * decay * recency_boost * protection
            if message["_session_sift"].get("protected"):
                weight = max(10.0, weight)
            message["_session_sift"]["structural_score"] = round(min(structure, 1.0), 4)
            message["_session_sift"]["retention_weight"] = round(weight, 4)

    def _structural_score(self, message: dict) -> float:
        text = safe_str(message.get("content", ""))
        score = 1.0
        if FILE_SIGNAL.search(text):
            score += 0.15
        if CODE_SIGNAL.search(text):
            score += 0.20
        if NUMBER_SIGNAL.search(text):
            score += 0.10
        if ERROR_SIGNAL.search(text):
            score += 0.10
        if "[SESSION SIFT: duplicate content" in text:
            score -= 0.50
        if "[SESSION SIFT SUMMARY" in text:
            score -= 0.10
        from session_sift.passes.pass3 import fluff_score

        if fluff_score(text) >= 0.70:
            score -= 0.30
        return max(0.5, min(score, 1.0))

    def _is_protected(self, content: str | list) -> bool:
        text = safe_str(content)
        return any(marker in text for marker in self.config.strict_protected)

    def _strip_metadata(self, messages: list[dict]) -> list[dict]:
        stripped: list[dict] = []
        for message in messages:
            updated = message.copy()
            updated.pop("_session_sift", None)
            stripped.append(updated)
        return stripped
