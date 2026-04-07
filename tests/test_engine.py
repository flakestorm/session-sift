from pathlib import Path

import pytest

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine


@pytest.mark.asyncio
async def test_engine_short_context_returns_unchanged(tmp_path: Path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    messages = [{"role": "user", "content": "hi"} for _ in range(3)]

    refined, report = await engine.refine(messages)

    assert refined == messages
    assert report.total_savings == 0


@pytest.mark.asyncio
async def test_engine_protects_system_and_recent_messages(tmp_path: Path) -> None:
    engine = SessionSiftEngine(
        SessionSiftConfig(registry_path=str(tmp_path / "registry.db"), recency_window=2)
    )
    messages = [{"role": "system", "content": "system prompt"}]
    messages.extend({"role": "user", "content": f"message {index}"} for index in range(10))

    annotated = engine._annotate(messages, 1)

    assert annotated[0]["_session_sift"]["protected"] is True
    assert annotated[-1]["_session_sift"]["protected"] is True
    assert annotated[-2]["_session_sift"]["protected"] is True


@pytest.mark.asyncio
async def test_engine_runs_deterministic_pipeline(tmp_path: Path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "```python\n" + "\n".join(f"line {i}" for i in range(60)) + "\n```"},
        {"role": "assistant", "content": "ok"},
        {"role": "assistant", "content": "ok2"},
        {"role": "assistant", "content": "ok3"},
        {"role": "assistant", "content": "ok4"},
        {"role": "assistant", "content": "ok5"},
        {"role": "assistant", "content": "ok6"},
        {"role": "assistant", "content": "ok7"},
        {"role": "assistant", "content": "ok8"},
    ]

    refined, report = await engine.refine(messages)

    assert len(refined) == len(messages)
    assert report.pass1_savings >= 0
    assert all("_session_sift" not in message for message in refined)


@pytest.mark.asyncio
async def test_engine_assigns_retention_weight_metadata(tmp_path: Path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db"), recency_window=1))
    messages = [{"role": "system", "content": "system prompt"}]
    messages.extend({"role": "assistant", "content": f"Great, sounds good {index}"} for index in range(40))

    await engine.refine(messages)

    annotated = engine._last_annotated
    assert annotated[0]["_session_sift"]["retention_weight"] >= 10.0
    assert any(item["_session_sift"]["retention_weight"] < 0.15 for item in annotated[1:])


@pytest.mark.asyncio
async def test_engine_status_and_append_turn(tmp_path: Path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))

    await engine.append_turn({"role": "assistant", "content": "hello"})

    status = engine.status()
    assert status["history_entries"] == 1
    assert status["registry_path"].endswith("registry.db")


@pytest.mark.asyncio
async def test_engine_pass2_failure_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db"), pass3_enabled=False))

    async def broken_run(messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine._pass2, "run", broken_run)
    refined, report = await engine.refine([{"role": "user", "content": f"hello {i}"} for i in range(10)])

    assert len(refined) == 10
    assert report.pass2_savings == 0


def test_engine_needs_pass3_and_structural_score() -> None:
    engine = SessionSiftEngine(SessionSiftConfig(pass3_enabled=True, max_context_tokens=8))
    message = {
        "role": "assistant",
        "content": "./src/app.py Traceback ValueError 55 def func(): pass with several extra tokens to exceed the threshold",
        "_session_sift": {"retention_weight": 1.0, "protected": False},
    }

    assert engine._needs_pass3([message]) is True
    assert engine._structural_score(message) == 1.0
    assert engine._is_protected("TODO keep this") is True
    assert engine._strip_metadata([{"role": "user", "content": "x", "_session_sift": {}}]) == [{"role": "user", "content": "x"}]


def test_engine_needs_pass3_disabled_returns_false() -> None:
    engine = SessionSiftEngine(SessionSiftConfig(pass3_enabled=False))
    assert engine._needs_pass3([{"role": "user", "content": "x", "_session_sift": {"retention_weight": 0.0}}]) is False
