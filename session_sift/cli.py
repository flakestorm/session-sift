from __future__ import annotations

import argparse
import asyncio
import json
from io import StringIO
from pathlib import Path

from aiohttp import web

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.models import SavingsReport
from session_sift.server_mcp import main as mcp_main
from session_sift.server_mcp import serve_stdio as mcp_serve_stdio
from session_sift.server_proxy import create_app


async def run_refine(args: argparse.Namespace) -> int:
    engine = SessionSiftEngine(SessionSiftConfig.load())
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    messages = payload["messages"] if isinstance(payload, dict) else payload
    refined, report = await engine.refine(messages, force_pass3=args.force_pass3)
    result = {"messages": refined, "report": report.to_dict()}
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not args.output:
        print(json.dumps(result, indent=2))
    if getattr(args, "report", False):
        print(report.to_console())
    return 0


async def run_export_dna(args: argparse.Namespace) -> int:
    engine = SessionSiftEngine(SessionSiftConfig.load())
    payload = await engine.export_dna(args.output)
    print(json.dumps(payload, indent=2))
    return 0


async def run_import_dna(args: argparse.Namespace) -> int:
    engine = SessionSiftEngine(SessionSiftConfig.load())
    payload = await engine.import_dna(args.input)
    print(json.dumps(payload, indent=2))
    return 0


async def run_status(_: argparse.Namespace) -> int:
    engine = SessionSiftEngine(SessionSiftConfig.load())
    payload = engine.status()
    payload["registry_entries"] = await engine._registry.count_entries()
    print(json.dumps(payload, indent=2))
    return 0


async def run_verify_mcp(_: argparse.Namespace) -> int:
    stdin = StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "session-sift-verify", "version": "0.1.0"},
                },
            },
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}, separators=(",", ":"))
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, separators=(",", ":"))
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "session_sift_status", "arguments": {}},
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    stdout = StringIO()

    await mcp_serve_stdio(SessionSiftConfig.load(), stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    initialize = next(item for item in responses if item.get("id") == 1)
    listing = next(item for item in responses if item.get("id") == 2)
    status_call = next(item for item in responses if item.get("id") == 3)
    tool_names = sorted(tool["name"] for tool in listing["result"]["tools"])
    status_payload = json.loads(status_call["result"]["content"][0]["text"])

    print(
        json.dumps(
            {
                "ok": True,
                "transport": "stdio",
                "protocol_version": initialize["result"]["protocolVersion"],
                "server_name": initialize["result"]["serverInfo"]["name"],
                "tools": tool_names,
                "status_tool_session_id": status_payload["session_id"],
            },
            indent=2,
        )
    )
    return 0


def run_report(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report_payload = payload.get("report", payload)
    report = SavingsReport(
        original_tokens=report_payload["original_tokens"],
        refined_tokens=report_payload["refined_tokens"],
        pass1_savings=report_payload["pass1_savings"],
        pass2_savings=report_payload["pass2_savings"],
        pass3_savings=report_payload["pass3_savings"],
        elapsed_ms=report_payload["elapsed_ms"],
        turn=report_payload["turn"],
        session_id=report_payload.get("session_id", ""),
    )
    print(report.to_console())
    return 0


def run_config(args: argparse.Namespace) -> int:
    config = SessionSiftConfig.load()
    if args.action == "show":
        print(json.dumps(config.to_dict(), indent=2))
        return 0
    if args.key is None:
        raise SystemExit("config key is required")
    if args.action == "get":
        print(json.dumps({args.key: getattr(config, args.key)}, indent=2))
        return 0
    if not hasattr(config, args.key):
        raise SystemExit(f"Unknown config key: {args.key}")
    setattr(config, args.key, SessionSiftConfig.coerce_value(args.key, args.value))
    path = config.save()
    print(json.dumps({"updated": args.key, "value": getattr(config, args.key), "path": str(path)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="session-sift")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refine = subparsers.add_parser("refine")
    refine.add_argument("input")
    refine.add_argument("--output")
    refine.add_argument("--force-pass3", action="store_true")
    refine.add_argument("--report", action="store_true")

    mcp = subparsers.add_parser("mcp")
    mcp.add_argument("--transport", choices=["stdio", "tcp"], default="stdio")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=9977)

    proxy = subparsers.add_parser("proxy")
    proxy.add_argument("--host", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=9978)
    proxy.add_argument("--provider", default="openai")
    proxy.add_argument("--upstream-url", default="https://api.openai.com")
    proxy.add_argument("--enable-pass3", action="store_true")

    cloud_api = subparsers.add_parser("cloud-api")
    cloud_api.add_argument("--host", default="127.0.0.1")
    cloud_api.add_argument("--port", type=int, default=9980)
    cloud_api.add_argument("--db-path", default=".session-sift/team-cloud.db")

    verify = subparsers.add_parser("verify")
    verify_subparsers = verify.add_subparsers(dest="verify_action", required=True)
    verify_subparsers.add_parser("mcp")

    status = subparsers.add_parser("status")

    report = subparsers.add_parser("report")
    report.add_argument("input")

    config = subparsers.add_parser("config")
    config_subparsers = config.add_subparsers(dest="action", required=True)
    config_show = config_subparsers.add_parser("show")
    config_show.set_defaults(key=None, value=None)
    config_get = config_subparsers.add_parser("get")
    config_get.add_argument("key")
    config_set = config_subparsers.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")

    dna = subparsers.add_parser("dna")
    dna_subparsers = dna.add_subparsers(dest="dna_action", required=True)
    dna_export = dna_subparsers.add_parser("export")
    dna_export.add_argument("--output", default=".session-sift/dna.json")
    dna_import = dna_subparsers.add_parser("import")
    dna_import.add_argument("input")

    dna = subparsers.add_parser("dna-export")
    dna.add_argument("--output", default=".session-sift/dna.json")

    dna_import = subparsers.add_parser("dna-import")
    dna_import.add_argument("input")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "refine":
        raise SystemExit(asyncio.run(run_refine(args)))
    if args.command == "mcp":
        config = SessionSiftConfig(mcp_host=args.host, mcp_port=args.port)
        raise SystemExit(asyncio.run(mcp_main(config, transport=args.transport)))
    if args.command == "proxy":
        config = SessionSiftConfig(
            proxy_host=args.host,
            proxy_port=args.port,
            upstream_provider=args.provider,
            upstream_url=args.upstream_url,
            pass3_enabled=args.enable_pass3,
        )
        app = create_app(config)
        web.run_app(app, host=config.proxy_host, port=config.proxy_port)
        return
    if args.command == "cloud-api":
        try:
            from session_sift.server_cloud import main as cloud_main
        except ImportError as exc:
            raise SystemExit(
                "FastAPI cloud dependencies are missing. Install with: pip install -e .[cloud]"
            ) from exc
        cloud_main(host=args.host, port=args.port, db_path=args.db_path)
        return
    if args.command == "verify":
        if args.verify_action == "mcp":
            raise SystemExit(asyncio.run(run_verify_mcp(args)))
    if args.command == "status":
        raise SystemExit(asyncio.run(run_status(args)))
    if args.command == "report":
        raise SystemExit(run_report(args))
    if args.command == "config":
        raise SystemExit(run_config(args))
    if args.command == "dna":
        if args.dna_action == "export":
            raise SystemExit(asyncio.run(run_export_dna(args)))
        if args.dna_action == "import":
            args.input = args.input
            raise SystemExit(asyncio.run(run_import_dna(args)))
    if args.command == "dna-export":
        raise SystemExit(asyncio.run(run_export_dna(args)))
    if args.command == "dna-import":
        raise SystemExit(asyncio.run(run_import_dna(args)))
    parser.error(f"Unknown command: {args.command}")
