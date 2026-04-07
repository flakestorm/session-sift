from session_sift.providers import Provider, extract_stream_text, normalize_request, resolve_provider


def test_resolve_provider_openclaw() -> None:
    assert resolve_provider("openclaw") == Provider.OPENCLAW


def test_normalize_request_for_anthropic() -> None:
    path, payload = normalize_request(
        Provider.ANTHROPIC,
        "/v1/chat/completions",
        {
            "model": "claude-test",
            "stream": True,
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
        },
    )

    assert path == "/v1/messages"
    assert payload["system"] == "system prompt"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]


def test_extract_stream_text_for_openai_like_stream() -> None:
    chunk = 'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
    assert extract_stream_text(Provider.OPENCLAW, chunk) == "hello"


def test_resolve_provider_defaults_and_aliases() -> None:
    assert resolve_provider(None) == Provider.OPENAI
    assert resolve_provider("openai-compatible-api") == Provider.OPENAI_COMPATIBLE


def test_resolve_provider_unsupported_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        resolve_provider("bogus")


def test_normalize_request_openai_like_passthrough() -> None:
    path, payload = normalize_request(Provider.OPENAI, "/v1/messages", {"messages": [{"role": "user", "content": "hi"}]})
    assert path == "/v1/chat/completions"
    assert payload["messages"][0]["content"] == "hi"


def test_extract_text_from_json_variants() -> None:
    from session_sift.providers import extract_text_from_json

    assert extract_text_from_json(Provider.OPENAI, {"choices": [{"message": {"content": [{"text": "a"}, {"text": "b"}]}}]}) == "ab"
    assert extract_text_from_json(Provider.ANTHROPIC, {"content": [{"text": "x"}, {"text": "y"}]}) == "xy"
    assert extract_text_from_json(Provider.ANTHROPIC, {"content": "z"}) == "z"


def test_extract_stream_text_for_anthropic_variants() -> None:
    chunk = '\n'.join(
        [
            'data: {"type":"content_block_delta","delta":{"text":"hello "}}',
            'data: {"type":"message_delta","delta":{"text":"world"}}',
            'data: [DONE]',
        ]
    )
    assert extract_stream_text(Provider.ANTHROPIC, chunk) == "hello world"


def test_extract_stream_text_ignores_invalid_json() -> None:
    assert extract_stream_text(Provider.OPENAI, 'data: {not-json}\n\n') == ""
