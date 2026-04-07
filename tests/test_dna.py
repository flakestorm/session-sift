from __future__ import annotations

import json
from pathlib import Path

import pytest

from session_sift.engine import SessionSiftEngine
from session_sift.config import SessionSiftConfig


@pytest.mark.asyncio
async def test_engine_can_import_and_export_dna(tmp_path: Path) -> None:
    source_file = tmp_path / "src"
    source_file.mkdir()
    app_file = source_file / "engine.py"
    app_file.write_text("# TODO: improve\ndef run():\n    return 1\n", encoding="utf-8")
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "files_modified": [
                    {"path": str(app_file), "last_write_turn": 42, "sha256": "abc123"}
                ]
            }
        ),
        encoding="utf-8",
    )
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))

    imported = await engine.import_dna(str(source))
    exported = await engine.export_dna(str(tmp_path / "out.json"))

    assert imported["imported_files"] == 1
    assert exported["files_modified"][0]["path"].endswith("engine.py")
    assert exported["files_modified"][0]["sha256"]
    assert "total_turns" in exported
    assert "context_summary" in exported
    assert exported["active_todos"][0]["file_path"].endswith("engine.py")


@pytest.mark.asyncio
async def test_engine_export_dna_includes_recent_decisions(tmp_path: Path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    engine._last_annotated = [
        {"content": "Chose SQLite over Redis for local state.", "_session_sift": {"turn_index": 23}},
        {"content": "plain text", "_session_sift": {"turn_index": 24}},
    ]

    exported = await engine.export_dna(str(tmp_path / "out.json"))

    assert exported["key_decisions"][0]["turn"] == 23
