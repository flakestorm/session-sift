from __future__ import annotations

import hashlib
import json

from session_sift.config import SessionSiftConfig
from session_sift.patterns import (
    CODE_FENCE,
    FILE_TREE,
    GIT_DIFF_HEADER,
    INSTALL_OUTPUT,
    LARGE_JSON,
    SESSION_SIFT_MARKER,
    STACK_TRACE_JAVA,
    STACK_TRACE_NODE,
    STACK_TRACE_PY,
    TOOL_RESULT_WRAP,
)


class StructuralPruner:
    def __init__(self, config: SessionSiftConfig) -> None:
        self.config = config
        self._content_hashes: dict[str, int] = {}

    def run(self, messages: list[dict]) -> tuple[list[dict], int]:
        total_before = sum(
            len(message["content"])
            for message in messages
            if isinstance(message.get("content"), str)
        )
        result: list[dict] = []
        for message in messages:
            if message["_session_sift"]["protected"]:
                result.append(message)
                continue
            result.append(self._process_message(message))
        total_after = sum(
            len(message["content"])
            for message in result
            if isinstance(message.get("content"), str)
        )
        savings = max(0, (total_before - total_after) // 4)
        return result, savings

    def _process_message(self, message: dict) -> dict:
        content = message.get("content", "")
        if not isinstance(content, str) or self._is_session_sift_marker(content):
            return message
        content = self._collapse_file_trees(content)
        content = self._collapse_stack_traces(content)
        content = self._collapse_large_json(content)
        content = self._collapse_code_fences(content)
        content = self._collapse_install_output(content)
        content = self._collapse_git_diff_headers(content)
        content = self._collapse_tool_scaffolding(content)
        content = self._dedup_content(content, message["_session_sift"]["index"])
        updated = message.copy()
        updated["content"] = content
        return updated

    def _is_session_sift_marker(self, text: str) -> bool:
        stripped = CODE_FENCE.sub("[CODE_BLOCK]", text)
        return bool(SESSION_SIFT_MARKER.search(stripped))

    def _collapse_file_trees(self, text: str) -> str:
        return FILE_TREE.sub(
            lambda match: f"[SESSION SIFT: file tree collapsed, {len(match.group(0).splitlines())} nodes]\n",
            text,
        )

    def _collapse_stack_traces(self, text: str) -> str:
        def replacer(match):
            lines = match.group(0).splitlines()
            frames = sum(1 for line in lines if line.strip().startswith(("at ", "File ")))
            return f"[SESSION SIFT: {frames}-frame traceback: {lines[-1]}]\n"

        for pattern in (STACK_TRACE_PY, STACK_TRACE_NODE, STACK_TRACE_JAVA):
            text = pattern.sub(replacer, text)
        return text

    def _collapse_large_json(self, text: str) -> str:
        def replacer(match):
            payload = match.group(0)
            try:
                data = json.loads(payload)
                size = len(data) if isinstance(data, (list, dict)) else 1
                kind = type(data).__name__
                return f"[SESSION SIFT: JSON {kind} collapsed, {size} top-level keys]\n"
            except json.JSONDecodeError:
                return f"[SESSION SIFT: large JSON collapsed, ~{len(payload)} chars]\n"

        return LARGE_JSON.sub(replacer, text)

    def _collapse_code_fences(self, text: str) -> str:
        def replacer(match):
            language = match.group("lang") or "unknown"
            body = match.group("body")
            line_count = body.count("\n") + 1
            if line_count <= 40:
                return match.group(0)
            return f"```{language}\n[SESSION SIFT: code block collapsed, {line_count} lines]\n```\n"

        return CODE_FENCE.sub(replacer, text)

    def _collapse_install_output(self, text: str) -> str:
        lines = text.splitlines()
        collapsed = []
        count = 0
        for line in lines:
            if INSTALL_OUTPUT.match(line):
                count += 1
                continue
            if count:
                collapsed.append(f"[SESSION SIFT: install output collapsed, {count} lines]")
                count = 0
            collapsed.append(line)
        if count:
            collapsed.append(f"[SESSION SIFT: install output collapsed, {count} lines]")
        return "\n".join(collapsed)

    def _collapse_git_diff_headers(self, text: str) -> str:
        lines = text.splitlines()
        kept: list[str] = []
        header_count = 0
        for line in lines:
            if GIT_DIFF_HEADER.match(line):
                header_count += 1
                continue
            kept.append(line)
        if header_count:
            kept.insert(0, f"[SESSION SIFT: git diff headers collapsed, {header_count} lines]")
        return "\n".join(kept)

    def _collapse_tool_scaffolding(self, text: str) -> str:
        match = TOOL_RESULT_WRAP.match(text)
        if not match:
            return text
        raw_content = match.group("content")
        try:
            extracted = json.loads(raw_content)
        except json.JSONDecodeError:
            return text
        if isinstance(extracted, list):
            return json.dumps(extracted, ensure_ascii=False)
        return str(extracted)

    def _dedup_content(self, text: str, index: int) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        if digest in self._content_hashes:
            first = self._content_hashes[digest]
            return f"[SESSION SIFT: duplicate content, identical to message at index {first}]"
        self._content_hashes[digest] = index
        return text
