from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.registry import FileRegistry
from session_sift.server_mcp import handle_request


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


async def benchmark_registry(write_count: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        registry = FileRegistry(str(Path(tmp_dir) / "registry.db"), session_id="benchmark")

        async def write_one(index: int) -> None:
            await registry.record_write(f"src/file_{index}.py", index, index, "write_file")

        start = time.perf_counter()
        await asyncio.gather(*(write_one(index) for index in range(write_count)))
        elapsed_ms = (time.perf_counter() - start) * 1000
        counts = await registry.count_entries()
        return {
            "writes": write_count,
            "elapsed_ms": round(elapsed_ms, 3),
            "writes_per_sec": round(write_count / max(elapsed_ms / 1000, 0.001), 2),
            "verified_count": counts["file_writes"],
        }


async def benchmark_mcp(call_count: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = SessionSiftEngine(SessionSiftConfig(registry_path=str(Path(tmp_dir) / "registry.db")))
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session_sift_refine",
                "params": {
                    "messages": [
                        {"role": "system", "content": "system prompt"},
                        *({"role": "user", "content": f"message {index}"} for index in range(10))
                    ]
                },
            }
        ).encode("utf-8")

        async def server_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await handle_request(reader, writer, engine)

        server = await asyncio.start_server(server_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        latencies: list[float] = []

        try:
            for _ in range(call_count):
                start = time.perf_counter()
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(payload)
                await writer.drain()
                await reader.read(65536)
                writer.close()
                await writer.wait_closed()
                latencies.append((time.perf_counter() - start) * 1000)
        finally:
            server.close()
            await server.wait_closed()

        return {
            "calls": call_count,
            "p50_ms": round(percentile(latencies, 50), 3),
            "p95_ms": round(percentile(latencies, 95), 3),
            "p99_ms": round(percentile(latencies, 99), 3),
            "max_ms": round(max(latencies) if latencies else 0.0, 3),
        }


async def main(call_count: int, write_count: int) -> None:
    result = {
        "registry": await benchmark_registry(write_count),
        "mcp": await benchmark_mcp(call_count),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure Session Sift registry concurrency and MCP latency.")
    parser.add_argument("--calls", type=int, default=200)
    parser.add_argument("--writes", type=int, default=1000)
    args = parser.parse_args()
    asyncio.run(main(args.calls, args.writes))