import pytest

from session_sift.config import SessionSiftConfig
import session_sift.passes.pass3 as pass3
from session_sift.passes.pass3 import SemanticCompressor, fluff_score


def test_fluff_score_detects_low_signal_text() -> None:
    score = fluff_score("Great, sounds good. I will now check this for you.")
    assert score >= 0.55


@pytest.mark.asyncio
async def test_pass3_compresses_fluff_but_preserves_numbers_and_paths() -> None:
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True))
    messages = [
        {
            "role": "assistant",
            "content": "Great, sounds good. I will now look at ./src/app.py and error 500 for you.",
            "_session_sift": {"turn": 5, "protected": False},
        }
    ]

    refined, savings = await compressor.run(messages)

    assert "SESSION SIFT SUMMARY" in refined[0]["content"]
    assert "./src/app.py" in refined[0]["content"]
    assert "500" in refined[0]["content"]
    assert savings > 0


@pytest.mark.asyncio
async def test_pass3_uses_retention_weight_threshold() -> None:
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True, pruning_threshold=0.15))
    messages = [
        {
            "role": "assistant",
            "content": "Concrete config value is 42 in ./src/app.py",
            "_session_sift": {"turn": 5, "protected": False, "retention_weight": 0.10},
        }
    ]

    refined, savings = await compressor.run(messages)

    assert "SESSION SIFT SUMMARY" in refined[0]["content"]
    assert savings >= 0


class _FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, headers):
        self.calls.append((url, json, headers))
        return self._response


@pytest.mark.asyncio
async def test_pass3_remote_anthropic_path(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(200, {"content": [{"text": "[SESSION SIFT SUMMARY - turns N-M]: ./src/app.py | 42"}]})
    session = _FakeSession(response)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(pass3, "ClientSession", lambda timeout=None: session)
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True, pass3_provider="anthropic"))
    messages = [
        {"role": "assistant", "content": "Great, I will now check ./src/app.py value 42", "_session_sift": {"turn": 5, "turn_index": 1, "index": 0, "protected": False, "retention_weight": 0.1}},
        {"role": "assistant", "content": "Okay, done", "_session_sift": {"turn": 5, "turn_index": 2, "index": 1, "protected": False, "retention_weight": 0.1}},
    ]

    refined, savings = await compressor.run(messages)

    assert refined[0]["content"].startswith("[SESSION SIFT SUMMARY - turns 1-2]:")
    assert savings >= 0
    assert session.calls[0][0].endswith("/v1/messages")


@pytest.mark.asyncio
async def test_pass3_remote_openai_like_path(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(200, {"choices": [{"message": {"content": "[SESSION SIFT SUMMARY - turns N-M]: 500 | ./src/app.py"}}]})
    session = _FakeSession(response)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(pass3, "ClientSession", lambda timeout=None: session)
    compressor = SemanticCompressor(
        SessionSiftConfig(pass3_enabled=True, pass3_provider="openai", pass3_api_key_env="ANTHROPIC_API_KEY")
    )
    messages = [
        {"role": "assistant", "content": "Great, I will now check ./src/app.py and 500", "_session_sift": {"turn": 5, "turn_index": 3, "index": 0, "protected": False, "retention_weight": 0.1}},
    ]

    refined, _ = await compressor.run(messages)

    assert refined[0]["content"].startswith("[SESSION SIFT SUMMARY - turns 3-3]:")
    assert session.calls[0][0].endswith("/v1/chat/completions")
    assert "Authorization" in session.calls[0][2]


@pytest.mark.asyncio
async def test_pass3_remote_failure_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(500, {})
    session = _FakeSession(response)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(pass3, "ClientSession", lambda timeout=None: session)
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True))
    messages = [
        {"role": "assistant", "content": "Great, sounds good. I will now check ./src/app.py and 500.", "_session_sift": {"turn": 5, "turn_index": 4, "index": 0, "protected": False, "retention_weight": 0.1}},
    ]

    refined, _ = await compressor.run(messages)

    assert "SESSION SIFT SUMMARY" in refined[0]["content"]


@pytest.mark.asyncio
async def test_pass3_run_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True, pass3_timeout_secs=0.01))

    async def broken_compress(messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(compressor, "_compress", broken_compress)
    messages = [{"role": "assistant", "content": "useful ./src/app.py", "_session_sift": {"protected": True, "turn": 1, "turn_index": 1, "index": 0}}]

    refined, savings = await compressor.run(messages)

    assert refined == messages
    assert savings == 0


@pytest.mark.asyncio
async def test_pass3_local_summary_keeps_original_when_empty_snippet() -> None:
    compressor = SemanticCompressor(SessionSiftConfig(pass3_enabled=True))
    message = {"role": "assistant", "content": "", "_session_sift": {"protected": False, "turn": 2, "turn_index": 2, "index": 0, "retention_weight": 0.0}}

    refined, savings = await compressor._compress([message])

    assert refined[0]["content"] == ""
    assert savings == 0
