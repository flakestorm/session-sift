from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class DNADiff:
    added_files: list[dict]
    removed_files: list[str]
    modified_files: list[dict]
    resolved_errors_delta: list[dict]
    new_todos: list[dict]
    resolved_todos: list[dict]
    decisions_delta: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def compute_diff(base: dict, local: dict, remote: dict) -> DNADiff:
    base_files = {entry["path"]: entry for entry in base.get("files_modified", []) if "path" in entry}
    local_files = {entry["path"]: entry for entry in local.get("files_modified", []) if "path" in entry}
    remote_files = {entry["path"]: entry for entry in remote.get("files_modified", []) if "path" in entry}
    all_paths = set(base_files) | set(local_files) | set(remote_files)

    added: list[dict] = []
    modified: list[dict] = []
    removed: list[str] = []

    for path in sorted(all_paths):
        in_base = path in base_files
        in_local = path in local_files
        in_remote = path in remote_files

        if not in_base and (in_local or in_remote):
            winner = _winner(local_files.get(path), remote_files.get(path))
            if winner is not None:
                added.append(winner)
            continue

        if in_base and not in_local and not in_remote:
            removed.append(path)
            continue

        if in_local and in_remote:
            left = local_files[path]
            right = remote_files[path]
            if left.get("sha256") != right.get("sha256"):
                modified.append(_winner(left, right) or left)

    merged_todos = _merge_dict_list_by_key(
        base.get("active_todos", []),
        local.get("active_todos", []),
        remote.get("active_todos", []),
        key="text",
    )

    return DNADiff(
        added_files=added,
        removed_files=[],
        modified_files=modified,
        resolved_errors_delta=list(local.get("resolved_errors", [])),
        new_todos=merged_todos,
        resolved_todos=[],
        decisions_delta=list(local.get("key_decisions", [])),
    )


def merge_dna(base: dict, local: dict, remote: dict) -> tuple[dict, str]:
    merged = dict(remote or {})
    merged.setdefault("$schema", local.get("$schema") or remote.get("$schema") or "https://session-sift.dev/dna/v2.json")
    merged["version"] = max(int(base.get("version", 2)), int(local.get("version", 2)), int(remote.get("version", 2)))

    merged["files_modified"] = _merge_files(
        base.get("files_modified", []),
        local.get("files_modified", []),
        remote.get("files_modified", []),
    )
    merged["resolved_errors"] = _merge_dict_list_by_key(
        base.get("resolved_errors", []),
        local.get("resolved_errors", []),
        remote.get("resolved_errors", []),
        key="file_path",
    )
    merged["active_todos"] = _merge_dict_list_by_key(
        base.get("active_todos", []),
        local.get("active_todos", []),
        remote.get("active_todos", []),
        key="text",
    )
    merged["key_decisions"] = _merge_decisions(
        base.get("key_decisions", []),
        local.get("key_decisions", []),
        remote.get("key_decisions", []),
    )
    merged["context_summary"] = local.get("context_summary") or remote.get("context_summary") or base.get("context_summary", "")
    merged["total_turns"] = max(
        int(base.get("total_turns", 0)),
        int(local.get("total_turns", 0)),
        int(remote.get("total_turns", 0)),
    )
    merged["total_tokens_saved"] = max(
        int(base.get("total_tokens_saved", 0)),
        int(local.get("total_tokens_saved", 0)),
        int(remote.get("total_tokens_saved", 0)),
    )

    merged_sha = hashlib.sha256(json.dumps(merged, sort_keys=True).encode("utf-8")).hexdigest()
    return merged, merged_sha


def _merge_files(base_files: list[dict], local_files: list[dict], remote_files: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for file_entry in list(base_files) + list(remote_files) + list(local_files):
        path = file_entry.get("path")
        if not path:
            continue
        current = merged.get(path)
        if current is None:
            merged[path] = file_entry
            continue
        merged[path] = _winner(current, file_entry) or file_entry
    return sorted(merged.values(), key=lambda entry: entry.get("path", ""))


def _merge_decisions(*decision_sets: list[dict]) -> list[dict]:
    merged: dict[tuple[int, str], dict] = {}
    for decisions in decision_sets:
        for decision in decisions:
            key = (int(decision.get("turn", 0)), str(decision.get("summary", "")))
            merged[key] = decision
    return [merged[key] for key in sorted(merged)]


def _merge_dict_list_by_key(*lists: list[dict], key: str) -> list[dict]:
    merged: dict[str, dict] = {}
    for entries in lists:
        for entry in entries:
            identity = str(entry.get(key, "")).strip()
            if identity:
                merged[identity] = entry
    return [merged[item_key] for item_key in sorted(merged)]


def _winner(left: dict | None, right: dict | None) -> dict | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if int(left.get("last_write_turn", 0)) >= int(right.get("last_write_turn", 0)) else right