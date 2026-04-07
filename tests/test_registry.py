from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from session_sift.registry import FileRegistry


@pytest.mark.asyncio
async def test_registry_concurrency_smoke(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")

    async def write_one(index: int) -> None:
        await registry.record_write(f"src/file_{index}.py", index, index, "write_file")

    await asyncio.gather(*(write_one(index) for index in range(100)))

    counts = await registry.count_entries()
    assert counts["file_writes"] == 100


@pytest.mark.asyncio
async def test_registry_records_and_queries_writes(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")

    await registry.record_write("src/app.py", turn=4, msg_index=2, tool_name="write_file")

    assert await registry.has_write_after("src/app.py", 4) is True
    assert await registry.has_write_after("src/app.py", 5) is False


@pytest.mark.asyncio
async def test_registry_exports_dna(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    output = tmp_path / "dna.json"

    await registry.record_write("src/server.py", turn=3, msg_index=1, tool_name="write_file")
    payload = await registry.export_dna(str(output))

    assert payload["session_id"] == "test"
    assert output.exists()


@pytest.mark.asyncio
async def test_registry_tracks_error_and_tombstone(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")

    await registry.record_error_reference("src/app.py", 1, 2, "SyntaxError")
    await registry.tombstone(1, "resolved_error")

    counts = await registry.count_entries()
    assert counts["file_writes"] == 0


@pytest.mark.asyncio
async def test_registry_helpers_and_context_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("# TODO ship\nclass App:\n    pass\n", encoding="utf-8")
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    await registry.record_write(str(file_path), turn=2, msg_index=1, tool_name="write_file")
    await registry.record_error_reference(str(file_path), msg_index=2, turn=1, error_type="ValueError")

    assert await registry.has_write_after(str(file_path), 1) is True
    assert await registry._resolved_turn_for(str(file_path), 1) == 2
    summary, digest = registry._summarize_path(str(file_path))
    assert summary == "class App:"
    assert digest

    todos = registry._collect_active_todos([{"path": str(file_path)}])
    assert todos[0]["line"] == 1
    decisions = registry._extract_key_decisions(
        [{"content": "We chose SQLite for local state.", "_session_sift": {"turn_index": 7}}]
    )
    assert decisions[0]["turn"] == 7
    assert "Session captured" in registry._build_context_summary({"total_turns": 1, "files_modified": [], "resolved_errors": [], "total_tokens_saved": 2})

    monkeypatch.setattr(Path, "read_text", lambda self, **kwargs: (_ for _ in ()).throw(OSError("nope")))
    assert registry._summarize_path(str(file_path)) == (None, None)


@pytest.mark.asyncio
async def test_registry_import_dna_snapshot_count(tmp_path: Path) -> None:
    registry = FileRegistry(str(tmp_path / "registry.db"), session_id="test")
    payload = {"files_modified": [{"path": "src/app.py", "last_write_turn": 3, "sha256": "abc"}]}
    input_path = tmp_path / "dna.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = await registry.import_dna(str(input_path))
    counts = await registry.count_entries()

    assert result["imported_files"] == 1
    assert counts["dna_snapshots"] == 1
