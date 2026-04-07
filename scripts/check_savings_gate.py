from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.benchmark_corpus import benchmark_fixture
from benchmarks.corpus_dataset import build_corpus


async def main(iterations: int, min_avg_savings_pct: float, corpus_size: int) -> int:
    fixtures = build_corpus(target_size=corpus_size)
    results = [await benchmark_fixture(fixture, iterations) for fixture in fixtures]
    avg_savings_pct = sum(item["avg_savings_pct"] for item in results) / max(len(results), 1)
    print(
        {
            "fixture_count": len(results),
            "iterations": iterations,
            "avg_savings_pct": round(avg_savings_pct, 3),
            "required_min_avg_savings_pct": min_avg_savings_pct,
        }
    )
    return 0 if avg_savings_pct >= min_avg_savings_pct else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fail CI if Session Sift average benchmark savings regress below a configured threshold.")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--min-avg-savings-pct", type=float, default=20.0)
    parser.add_argument("--corpus-size", type=int, default=50)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.iterations, args.min_avg_savings_pct, args.corpus_size)))