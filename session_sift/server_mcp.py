from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine


PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "session-sift", "version": "0.1.0"}

OPENRPC_SCHEMA = {
    "openrpc": "1.3.2",
    "info": {"title": "Session Sift MCP Server", "version": "2.0.0"},
    "methods": [
        {
            "name": "session_sift_refine",
            "summary": "Prune and compress the current conversation context",
            "params": [
                {"name": "messages", "required": True},
                {"name": "options", "required": False},
            ],
            "result": {"name": "SessionSiftResult"},
        },
        {
            "name": "session_sift_status",
            "summary": "Return current SessionSiftEngine stats",
            "result": {"name": "StatusResult"},
        },
        {
            "name": "session_sift_export_dna",
            "summary": "Export Project DNA to .session-sift/dna.json",
            "result": {"name": "ExportResult"},
        },
        {
            "name": "session_sift_openrpc",
            "summary": "Return the server OpenRPC schema",
            "result": {"name": "OpenRPCDocument"},
        },
    ],
}

TOOLS = [
    {
        "name": "session_sift_refine",
        "description": "Prune and compress a conversation transcript before it reaches the model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string"},
                            "content": {},
                        },
                        "required": ["role", "content"],
                    },
                },
                "force_pass3": {"type": "boolean", "default": False},
            },
            "required": ["messages"],
        },
        "_meta": {"anthropic/maxResultSizeChars": 500000},
    },
    {
        "name": "session_sift_status",
        "description": "Return the current Session Sift runtime status for this MCP server process.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "session_sift_export_dna",
        "description": "Export Project DNA for the current session to disk and return the snapshot metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
            },
        },
    },
]


@dataclass(slots=True)
class MCPSessionState:
    initialize_seen: bool = False
    initialized_notification_seen: bool = False


def _jsonrpc_result(message_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str, data: Any | None = None) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _tool_result(payload: Any, *, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"), ensure_ascii=True)}],
        "isError": is_error,
    }


async def process_jsonrpc_message(
    message: dict | list,
    engine: SessionSiftEngine,
    state: MCPSessionState,
) -> dict | list[dict] | None:
    if isinstance(message, list):
        responses: list[dict] = []
        for item in message:
            response = await process_jsonrpc_message(item, engine, state)
            if response is None:
                continue
            if isinstance(response, list):
                responses.extend(response)
            else:
                responses.append(response)
        return responses or None

    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})

    if method is None:
        return None

    try:
        if method == "initialize":
            requested_version = params.get("protocolVersion", PROTOCOL_VERSION)
            state.initialize_seen = True
            return _jsonrpc_result(
                request_id,
                {
                    "protocolVersion": requested_version if isinstance(requested_version, str) else PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": (
                        "Session Sift exposes transcript-pruning tools. Use session_sift_refine when the conversation is long, noisy, or near context limits."
                    ),
                },
            )

        if method == "notifications/initialized":
            state.initialized_notification_seen = True
            return None

        if method == "ping":
            return _jsonrpc_result(request_id, {})

        if method == "tools/list":
            return _jsonrpc_result(request_id, {"tools": TOOLS})

        if method == "tools/call":
            return _jsonrpc_result(request_id, await _call_tool(params, engine))

        if method == "session_sift_refine":
            messages = params.get("messages", [])
            options = params.get("options", {})
            refined, report = await engine.refine(messages, **options)
            return _jsonrpc_result(request_id, {"messages": refined, "report": report.to_dict()})

        if method == "session_sift_status":
            return _jsonrpc_result(request_id, engine.status())

        if method == "session_sift_export_dna":
            return _jsonrpc_result(request_id, await engine.export_dna(engine.config.dna_path))

        if method == "session_sift_openrpc":
            return _jsonrpc_result(request_id, OPENRPC_SCHEMA)

        return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
    except LookupError as exc:
        return _jsonrpc_error(request_id, -32602, str(exc))
    except ValueError as exc:
        return _jsonrpc_error(request_id, -32602, str(exc))
    except Exception as exc:
        return _jsonrpc_error(request_id, -32001, str(exc))


async def _call_tool(params: dict, engine: SessionSiftEngine) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {}) or {}

    if name == "session_sift_refine":
        messages = arguments.get("messages")
        if not isinstance(messages, list):
            raise ValueError("session_sift_refine requires a messages array")
        refined, report = await engine.refine(messages, force_pass3=bool(arguments.get("force_pass3", False)))
        return _tool_result({"messages": refined, "report": report.to_dict()})

    if name == "session_sift_status":
        return _tool_result(engine.status())

    if name == "session_sift_export_dna":
        output_path = arguments.get("output_path") if isinstance(arguments, dict) else None
        payload = await engine.export_dna(output_path)
        return _tool_result(payload)

    raise ValueError(f"Unknown tool: {name}")


async def handle_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    engine: SessionSiftEngine,
) -> None:
    raw = await reader.read(1_048_576)
    try:
        request = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        payload = _jsonrpc_error(None, -32700, f"Parse error: {exc}")
    else:
        payload = await process_jsonrpc_message(request, engine, MCPSessionState())
        if payload is None:
            payload = _jsonrpc_result(None, {})
    writer.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def serve_stdio(
    config: SessionSiftConfig | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    runtime_config = config or SessionSiftConfig()
    engine = SessionSiftEngine(runtime_config)
    state = MCPSessionState()
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout

    while True:
        line = await asyncio.to_thread(input_stream.readline)
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _jsonrpc_error(None, -32700, f"Parse error: {exc}")
        else:
            response = await process_jsonrpc_message(request, engine, state)
        if response is None:
            continue
        output_stream.write(json.dumps(response, separators=(",", ":"), ensure_ascii=True) + "\n")
        output_stream.flush()


async def serve_tcp(config: SessionSiftConfig | None = None) -> None:
    runtime_config = config or SessionSiftConfig()
    engine = SessionSiftEngine(runtime_config)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_request(reader, writer, engine)

    server = await asyncio.start_server(handler, runtime_config.mcp_host, runtime_config.mcp_port)
    async with server:
        await server.serve_forever()


async def main(config: SessionSiftConfig | None = None, *, transport: str = "stdio") -> None:
    if transport == "tcp":
        await serve_tcp(config)
        return
    await serve_stdio(config)


if __name__ == "__main__":
    asyncio.run(main())
