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
from benchmarks.corpus_dataset import build_corpus


async def benchmark_fixture(fixture: dict, iterations: int) -> dict:
    elapsed_values: list[float] = []
    total_savings: list[int] = []
    pass1_savings: list[int] = []
    pass2_savings: list[int] = []
    pass3_savings: list[int] = []
    savings_pct: list[float] = []

    for iteration in range(iterations):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = SessionSiftConfig(
                registry_path=str(Path(tmp_dir) / f"{fixture['name']}-{iteration}.db"),
                **fixture.get("config", {}),
            )
            engine = SessionSiftEngine(config)
            start = time.perf_counter()
            _, report = await engine.refine(
                fixture["messages"],
                force_pass3=fixture.get("force_pass3", False),
            )
            elapsed_values.append((time.perf_counter() - start) * 1000)
            total_savings.append(report.total_savings)
            pass1_savings.append(report.pass1_savings)
            pass2_savings.append(report.pass2_savings)
            pass3_savings.append(report.pass3_savings)
            savings_pct.append(report.savings_pct)

    return {
        "fixture": fixture["name"],
        "iterations": iterations,
        "avg_elapsed_ms": round(sum(elapsed_values) / iterations, 3),
        "avg_total_savings": round(sum(total_savings) / iterations, 2),
        "avg_pass1_savings": round(sum(pass1_savings) / iterations, 2),
        "avg_pass2_savings": round(sum(pass2_savings) / iterations, 2),
        "avg_pass3_savings": round(sum(pass3_savings) / iterations, 2),
        "avg_savings_pct": round(sum(savings_pct) / iterations, 3),
    }


async def main(iterations: int) -> None:
    fixtures = build_corpus(target_size=50)
    results = [await benchmark_fixture(fixture, iterations) for fixture in fixtures]
    summary = {
        "fixture_count": len(results),
        "iterations": iterations,
        "avg_elapsed_ms": round(sum(item["avg_elapsed_ms"] for item in results) / max(len(results), 1), 3),
        "avg_savings_pct": round(sum(item["avg_savings_pct"] for item in results) / max(len(results), 1), 3),
    }
    print(json.dumps({"summary": summary, "fixtures": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Session Sift against the curated fixture corpus.")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.iterations))