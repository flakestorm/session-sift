import runpy


def test_server_mcp_module_entrypoint(monkeypatch) -> None:
    called = {}

    def fake_run(coroutine):
        coroutine.close()
        called["ran"] = True

    monkeypatch.setattr("asyncio.run", fake_run)

    runpy.run_module("session_sift.server_mcp", run_name="__main__")

    assert called["ran"] is True


def test_server_proxy_module_entrypoint(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("aiohttp.web.run_app", lambda app, host, port: calls.append((app, host, port)))

    runpy.run_module("session_sift.server_proxy", run_name="__main__")

    assert calls[0][1] == "127.0.0.1"
    assert calls[0][2] == 9978