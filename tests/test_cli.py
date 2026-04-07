import json
import sys
from pathlib import Path

import pytest

import session_sift.cli as cli
from session_sift.cli import build_parser, run_config, run_refine, run_report, run_status, run_verify_mcp


@pytest.mark.asyncio
async def test_cli_refine_writes_output(tmp_path: Path) -> None:
    input_path = tmp_path / "session.json"
    output_path = tmp_path / "refined.json"
    payload = {"messages": [{"role": "user", "content": "hello"} for _ in range(3)]}
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    class Args:
        input = str(input_path)
        output = str(output_path)
        force_pass3 = False

    exit_code = await run_refine(Args())

    assert exit_code == 0
    assert output_path.exists()


def test_cli_config_set_and_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    class SetArgs:
        action = "set"
        key = "decay_lambda"
        value = "0.08"

    class GetArgs:
        action = "get"
        key = "decay_lambda"
        value = None

    assert run_config(SetArgs()) == 0
    assert run_config(GetArgs()) == 0
    captured = capsys.readouterr().out
    assert "0.08" in captured


@pytest.mark.asyncio
async def test_cli_status_outputs_registry_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    class Args:
        pass

    exit_code = await run_status(Args())
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "registry_entries" in captured


def test_cli_run_report_renders_console_output(tmp_path: Path, capsys) -> None:
    payload = tmp_path / "report.json"
    payload.write_text(
        json.dumps(
            {
                "report": {
                    "original_tokens": 100,
                    "refined_tokens": 50,
                    "pass1_savings": 10,
                    "pass2_savings": 20,
                    "pass3_savings": 20,
                    "elapsed_ms": 12.3,
                    "turn": 4,
                }
            }
        ),
        encoding="utf-8",
    )

    class Args:
        input = str(payload)

    assert run_report(Args()) == 0
    assert "SESSION SIFT SAVINGS REPORT" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cli_run_export_and_import_dna(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    export_args = type("Args", (), {"output": str(tmp_path / "dna.json")})
    import_args = type("Args", (), {"input": str(tmp_path / "dna.json")})

    assert await cli.run_export_dna(export_args) == 0
    assert json.loads(capsys.readouterr().out)["session_id"]
    assert await cli.run_import_dna(import_args) == 0
    assert json.loads(capsys.readouterr().out)["imported_files"] >= 0


def test_cli_run_config_get_and_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    class GetArgs:
        action = "get"
        key = "token_threshold"
        value = None

    assert run_config(GetArgs()) == 0
    assert "token_threshold" in capsys.readouterr().out

    class MissingArgs:
        action = "get"
        key = None
        value = None

    with pytest.raises(SystemExit):
        run_config(MissingArgs())


def test_build_parser_supports_expected_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(["config", "set", "decay_lambda", "0.09"])

    assert args.command == "config"
    assert args.action == "set"
    assert args.key == "decay_lambda"


@pytest.mark.asyncio
async def test_cli_verify_mcp_outputs_tools(capsys) -> None:
    class Args:
        pass

    exit_code = await run_verify_mcp(Args())
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["ok"] is True
    assert "session_sift_refine" in captured["tools"]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["session-sift", "refine", "session.json"], "refine"),
        (["session-sift", "mcp"], "mcp"),
        (["session-sift", "verify", "mcp"], "verify-mcp"),
        (["session-sift", "cloud-api"], "cloud-api"),
        (["session-sift", "status"], "status"),
        (["session-sift", "report", "report.json"], "report"),
        (["session-sift", "config", "show"], "config"),
        (["session-sift", "dna", "export"], "dna-export"),
        (["session-sift", "dna", "import", "dna.json"], "dna-import"),
        (["session-sift", "dna-export"], "dna-export-alias"),
        (["session-sift", "dna-import", "dna.json"], "dna-import-alias"),
    ],
)
def test_cli_main_dispatches(monkeypatch: pytest.MonkeyPatch, argv, expected) -> None:
    calls: list[str] = []

    async def fake_async(_args):
        calls.append(expected)
        return 0

    async def fake_mcp(_config, *, transport="stdio"):
        calls.append("mcp")
        return 0

    def fake_cloud(*, host, port, db_path):
        calls.append("cloud-api")

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "run_refine", fake_async)
    monkeypatch.setattr(cli, "run_status", fake_async)
    monkeypatch.setattr(cli, "run_verify_mcp", fake_async)
    monkeypatch.setattr(cli, "run_export_dna", fake_async)
    monkeypatch.setattr(cli, "run_import_dna", fake_async)
    monkeypatch.setattr(cli, "mcp_main", fake_mcp)
    monkeypatch.setattr(cli, "run_report", lambda _args: calls.append("report") or 0)
    monkeypatch.setattr(cli, "run_config", lambda _args: calls.append("config") or 0)
    monkeypatch.setattr(cli.web, "run_app", lambda *args, **kwargs: calls.append("proxy"))
    monkeypatch.setattr(cli, "create_app", lambda config: object())
    monkeypatch.setitem(sys.modules, "session_sift.server_cloud", type("CloudModule", (), {"main": fake_cloud}))

    if expected == "cloud-api":
        cli.main()
    else:
        with pytest.raises(SystemExit):
            cli.main()

    if expected == "mcp":
        assert calls == ["mcp"]
    elif expected == "verify-mcp":
        assert calls == ["verify-mcp"]
    elif expected == "report":
        assert calls == ["report"]
    elif expected == "config":
        assert calls == ["config"]
    else:
        assert calls == [expected]


def test_cli_main_proxy_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(sys, "argv", ["session-sift", "proxy", "--provider", "anthropic"])
    monkeypatch.setattr(cli, "create_app", lambda config: calls.append(("app", config)) or object())
    monkeypatch.setattr(cli.web, "run_app", lambda app, host, port: calls.append(("run", (host, port))))

    cli.main()

    assert calls[0][0] == "app"
    assert calls[0][1].upstream_provider == "anthropic"
    assert calls[1] == ("run", ("127.0.0.1", 9978))


def test_cli_main_mcp_stdio_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    async def fake_mcp(config, *, transport="stdio"):
        calls.append(("mcp", (config.mcp_host, config.mcp_port, transport)))
        return 0

    monkeypatch.setattr(sys, "argv", ["session-sift", "mcp"])
    monkeypatch.setattr(cli, "mcp_main", fake_mcp)

    with pytest.raises(SystemExit):
        cli.main()

    assert calls == [("mcp", ("127.0.0.1", 9977, "stdio"))]


def test_cli_main_cloud_api_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_cloud(*, host, port, db_path):
        calls.append(("cloud", (host, port, db_path)))

    monkeypatch.setattr(sys, "argv", ["session-sift", "cloud-api", "--port", "9988"])
    monkeypatch.setitem(sys.modules, "session_sift.server_cloud", type("CloudModule", (), {"main": fake_cloud}))

    cli.main()

    assert calls == [("cloud", ("127.0.0.1", 9988, ".session-sift/team-cloud.db"))]


def test_cli_main_unknown_command_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeParser:
        def parse_args(self):
            return type("Args", (), {"command": "wat"})()

        def error(self, message):
            raise RuntimeError(message)

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser())

    with pytest.raises(RuntimeError, match="Unknown command: wat"):
        cli.main()


def test_cli_run_config_invalid_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    class Args:
        action = "set"
        key = "nope"
        value = "1"

    with pytest.raises(SystemExit):
        run_config(Args())