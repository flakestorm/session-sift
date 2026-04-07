from __future__ import annotations

import re

from session_sift.config import SessionSiftConfig
from session_sift.registry import FileRegistry
from session_sift.utils import safe_str


FILE_PATH_IN_ERROR = re.compile(
    r"(?:File [\"']?|in |at |from )?(\.{0,2}/[^\s:\"'>]+\.[a-zA-Z]{1,8}|[A-Za-z]:/[^\s:\"'>]+\.[a-zA-Z]{1,8})"
)

WRITE_TOOL_NAMES = {
    "write_file",
    "str_replace_editor",
    "create_file",
    "apply_patch",
    "edit_file",
    "overwrite_file",
}


class TemporalPruner:
    def __init__(self, config: SessionSiftConfig, registry: FileRegistry) -> None:
        self.config = config
        self.registry = registry

    async def run(self, messages: list[dict]) -> tuple[list[dict], int]:
        await self._register_writes(messages)
        error_map = await self._extract_errors(messages)
        to_prune: set[int] = set()
        for msg_index, file_path, turn, error_type in error_map:
            if await self.registry.has_write_after(file_path, turn):
                to_prune.add(msg_index)
                await self.registry.tombstone(msg_index, "resolved_error")
            await self.registry.record_error_reference(file_path, msg_index, turn, error_type)

        result: list[dict] = []
        savings = 0
        for message in messages:
            idx = message["_session_sift"]["index"]
            if idx in to_prune and not message["_session_sift"]["protected"]:
                savings += len(safe_str(message.get("content", ""))) // 4
                updated = message.copy()
                updated["content"] = (
                    f"[SESSION SIFT: resolved error pruned at turn {message['_session_sift']['turn']}]"
                )
                result.append(updated)
                continue
            result.append(message)
        return result, savings

    async def _register_writes(self, messages: list[dict]) -> None:
        for message in messages:
            content = message.get("content", "")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                if name not in WRITE_TOOL_NAMES:
                    continue
                for path in self._extract_paths_from_tool_input(block.get("input", {})):
                    await self.registry.record_write(
                        file_path=path,
                        turn=message["_session_sift"]["turn"],
                        msg_index=message["_session_sift"]["index"],
                        tool_name=name,
                    )

    async def _extract_errors(self, messages: list[dict]) -> list[tuple[int, str, int, str | None]]:
        error_map: list[tuple[int, str, int, str | None]] = []
        for message in messages:
            content = safe_str(message.get("content", ""))
            if not any(token in content for token in ["Error", "Exception", "Traceback", "FAILED"]):
                continue
            paths = FILE_PATH_IN_ERROR.findall(content)
            if not paths:
                continue
            error_type = self._extract_error_type(content)
            error_map.append(
                (
                    message["_session_sift"]["index"],
                    paths[0],
                    message["_session_sift"]["turn"],
                    error_type,
                )
            )
        return error_map

    def _extract_paths_from_tool_input(self, payload: dict) -> list[str]:
        paths: list[str] = []
        if not isinstance(payload, dict):
            return paths
        if "path" in payload and payload["path"]:
            paths.append(payload["path"])
        for key in ("files", "changes"):
            values = payload.get(key, [])
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict) and value.get("path"):
                    paths.append(value["path"])
        return paths

    def _extract_error_type(self, content: str) -> str | None:
        match = re.search(r"([A-Za-z_]+(?:Error|Exception))", content)
        return match.group(1) if match else None
