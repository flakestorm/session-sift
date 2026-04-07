from __future__ import annotations

import json
from pathlib import Path

import pytest

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.utils import safe_str


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sessions"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_messages(messages: list[dict]) -> str:
    return "\n".join(safe_str(message.get("content", "")) for message in messages)


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem)
@pytest.mark.asyncio
async def test_session_fixture_corpus_regressions(fixture_path: Path, tmp_path: Path) -> None:
    fixture = _load_fixture(fixture_path)
    config = SessionSiftConfig(
        registry_path=str(tmp_path / f"{fixture['name']}.db"),
        **fixture.get("config", {}),
    )
    engine = SessionSiftEngine(config)

    refined, report = await engine.refine(
        fixture["messages"],
        force_pass3=fixture.get("force_pass3", False),
    )

    expectations = fixture["expectations"]
    rendered = _render_messages(refined)

    assert len(fixture["messages"]) >= 10
    assert report.total_savings >= expectations.get("min_total_savings", 0)
    assert report.pass1_savings >= expectations.get("min_pass1_savings", 0)
    assert report.pass2_savings >= expectations.get("min_pass2_savings", 0)
    assert report.pass3_savings >= expectations.get("min_pass3_savings", 0)

    for marker in expectations.get("markers", []):
        assert marker in rendered
    for snippet in expectations.get("preserved", []):
        assert snippet in rendered


def test_session_fixture_corpus_is_present() -> None:
    assert [path.stem for path in FIXTURE_PATHS] == [
        "resolved_error",
        "semantic_compression",
        "structural_pruning",
    ]