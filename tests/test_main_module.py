import runpy


def test_main_module_executes(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr("session_sift.cli.main", lambda: called.setdefault("ran", True))

    runpy.run_module("session_sift.__main__", run_name="__main__")

    assert called["ran"] is True