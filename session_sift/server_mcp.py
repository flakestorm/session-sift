from __future__ import annotations

import asyncio
import json

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine


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


async def handle_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    engine: SessionSiftEngine,
) -> None:
    raw = await reader.read(1_048_576)
    request_id = 1
    try:
        request = json.loads(raw.decode("utf-8"))
        request_id = request.get("id", 1)
        method = request.get("method")
        params = request.get("params", {})
        if method == "session_sift_refine":
            messages = params.get("messages", [])
            options = params.get("options", {})
            refined, report = await engine.refine(messages, **options)
            result = {"messages": refined, "report": report.to_dict()}
        elif method == "session_sift_status":
            result = engine.status()
        elif method == "session_sift_export_dna":
            result = await engine._registry.export_dna(engine.config.dna_path)
        elif method == "session_sift_openrpc":
            result = OPENRPC_SCHEMA
        else:
            raise ValueError(f"Unknown method: {method}")
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32001, "message": str(exc)},
        }
    writer.write(json.dumps(payload).encode("utf-8"))
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main(config: SessionSiftConfig | None = None) -> None:
    runtime_config = config or SessionSiftConfig()
    engine = SessionSiftEngine(runtime_config)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_request(reader, writer, engine)

    server = await asyncio.start_server(
        handler, runtime_config.mcp_host, runtime_config.mcp_port
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
