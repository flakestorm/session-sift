from __future__ import annotations

import asyncio
import time

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine


async def main() -> None:
    engine = SessionSiftEngine(SessionSiftConfig(registry_path=".session-sift/benchmark-registry.db"))
    body = "\n".join(f"line {index}" for index in range(80))
    messages = [{"role": "system", "content": "system prompt"}]
    for index in range(20):
        content = f"```python\n{body}\n```" if index == 5 else f"message {index}"
        messages.append({"role": "user", "content": content})

    start = time.perf_counter()
    refined, report = await engine.refine(messages)
    elapsed = (time.perf_counter() - start) * 1000
    print({
        "elapsed_ms": elapsed,
        "report": report.to_dict(),
        "refined_messages": len(refined),
    })


if __name__ == "__main__":
    asyncio.run(main())