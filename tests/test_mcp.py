from __future__ import annotations

import asyncio
import json
from io import StringIO

import pytest

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.server_mcp import MCPSessionState, handle_request, process_jsonrpc_message, serve_stdio


@pytest.mark.asyncio
async def test_mcp_initialize_and_tools_list() -> None:
    engine = SessionSiftEngine(SessionSiftConfig())
    state = MCPSessionState()

    initialize = await process_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        },
        engine,
        state,
    )
    assert initialize["result"]["capabilities"]["tools"]["listChanged"] is False

    listing = await process_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        engine,
        state,
    )
    tool_names = {tool["name"] for tool in listing["result"]["tools"]}
    assert {"session_sift_refine", "session_sift_status", "session_sift_export_dna"}.issubset(tool_names)


@pytest.mark.asyncio
async def test_mcp_tools_call_refine() -> None:
    engine = SessionSiftEngine(SessionSiftConfig())
    state = MCPSessionState()
    await process_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1.0.0"}},
        },
        engine,
        state,
    )

    response = await process_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "session_sift_refine",
                "arguments": {
                    "messages": [{"role": "user", "content": f"message {index}"} for index in range(10)]
                },
            },
        },
        engine,
        state,
    )
    tool_payload = json.loads(response["result"]["content"][0]["text"])
    assert tool_payload["report"]["turn"] == 1
    assert len(tool_payload["messages"]) == 10


@pytest.mark.asyncio
async def test_mcp_stdio_transport_processes_newline_messages() -> None:
    stdin = StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1.0.0"}},
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    stdout = StringIO()

    await serve_stdio(SessionSiftConfig(), stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert responses[0]["result"]["serverInfo"]["name"] == "session-sift"
    assert any(tool["name"] == "session_sift_refine" for tool in responses[1]["result"]["tools"])


@pytest.mark.asyncio
async def test_mcp_handle_refine_request(tmp_path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session_sift_refine",
        "params": {
            "messages": [{"role": "user", "content": f"message {index}"} for index in range(10)]
        },
    }

    server_result = {}

    async def server_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_request(reader, writer, engine)

    server = await asyncio.start_server(server_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(json.dumps(payload).encode("utf-8"))
        await writer.drain()
        raw = await reader.read(65536)
        server_result = json.loads(raw.decode("utf-8"))
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert server_result["result"]["report"]["turn"] == 1
    assert len(server_result["result"]["messages"]) == 10


@pytest.mark.asyncio
async def test_mcp_exposes_openrpc_schema(tmp_path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    payload = {"jsonrpc": "2.0", "id": 2, "method": "session_sift_openrpc", "params": {}}

    async def server_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_request(reader, writer, engine)

    server = await asyncio.start_server(server_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(json.dumps(payload).encode("utf-8"))
        await writer.drain()
        raw = await reader.read(65536)
        response = json.loads(raw.decode("utf-8"))
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert response["result"]["openrpc"] == "1.3.2"
    assert any(method["name"] == "session_sift_refine" for method in response["result"]["methods"])


@pytest.mark.asyncio
async def test_mcp_unknown_method_returns_error(tmp_path) -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(tmp_path / "registry.db")))
    payload = {"jsonrpc": "2.0", "id": 3, "method": "bogus", "params": {}}

    async def server_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_request(reader, writer, engine)

    server = await asyncio.start_server(server_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(json.dumps(payload).encode("utf-8"))
        await writer.drain()
        raw = await reader.read(65536)
        response = json.loads(raw.decode("utf-8"))
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_main_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    started = {}

    class FakeServer:
        async def __aenter__(self):
            started["entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def serve_forever(self):
            started["served"] = True

    async def fake_start_server(handler, host, port):
        started["host"] = host
        started["port"] = port
        return FakeServer()

    monkeypatch.setattr("session_sift.server_mcp.asyncio.start_server", fake_start_server)

    await __import__("session_sift.server_mcp", fromlist=["main"]).main(SessionSiftConfig(mcp_host="127.0.0.1", mcp_port=9999), transport="tcp")

    assert started["host"] == "127.0.0.1"
    assert started["port"] == 9999
    assert started["entered"] is True
    assert started["served"] is True