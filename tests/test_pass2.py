from pathlib import Path

import pytest

from session_sift.config import SessionSiftConfig
from session_sift.passes.pass2 import TemporalPruner
from session_sift.registry import FileRegistry


@pytest.mark.asyncio
async def test_pass2_prunes_resolved_error(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    pruner = TemporalPruner(SessionSiftConfig(), registry)
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "write_file",
                    "input": {"path": "src/main.py"},
                }
            ],
            "_session_sift": {"turn": 1, "index": 0, "protected": False},
        },
        {
            "role": "assistant",
            "content": "Traceback (most recent call last):\nFile ./src/main.py, line 1\nValueError: boom",
            "_session_sift": {"turn": 1, "index": 1, "protected": False},
        },
    ]

    refined, savings = await pruner.run(messages)

    assert "resolved error pruned" in refined[1]["content"]
    assert savings > 0


@pytest.mark.asyncio
async def test_pass2_skips_protected_messages(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    pruner = TemporalPruner(SessionSiftConfig(), registry)
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "write_file",
                    "input": {"path": "src/main.py"},
                }
            ],
            "_session_sift": {"turn": 1, "index": 0, "protected": False},
        },
        {
            "role": "assistant",
            "content": "Traceback (most recent call last):\nFile ./src/main.py, line 1\nValueError: boom STRICT",
            "_session_sift": {"turn": 1, "index": 1, "protected": True},
        },
    ]

    refined, _ = await pruner.run(messages)

    assert refined[1]["content"].endswith("STRICT")


@pytest.mark.asyncio
async def test_pass2_extract_helpers_cover_non_matches(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    pruner = TemporalPruner(SessionSiftConfig(), registry)

    assert pruner._extract_paths_from_tool_input("nope") == []
    assert pruner._extract_paths_from_tool_input({"files": "bad", "changes": "bad"}) == []
    assert pruner._extract_error_type("all good") is None

    messages = [{"role": "assistant", "content": "ValueError: boom", "_session_sift": {"index": 1, "turn": 2, "protected": False}}]
    assert await pruner._extract_errors(messages) == []
