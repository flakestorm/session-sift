from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.corpus_dataset import build_corpus
from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.utils import safe_str


def parse_candidate(value: str) -> dict:
    provider, model, env_var, base_url = value.split("|", 3)
    return {
        "provider": provider,
        "model": model,
        "env_var": env_var,
        "base_url": base_url,
    }


def preservation_score(expectations: dict, refined_messages: list[dict]) -> float:
    preserved = expectations.get("preserved", [])
    if not preserved:
        return 1.0
    rendered = "\n".join(safe_str(message.get("content", "")) for message in refined_messages)
    hits = sum(1 for token in preserved if token in rendered)
    return hits / len(preserved)


async def run_candidate(candidate: dict, iterations: int) -> dict:
    if not os.getenv(candidate["env_var"]):
        return {
            "provider": candidate["provider"],
            "model": candidate["model"],
            "status": "skipped",
            "reason": f"missing env var {candidate['env_var']}",
        }

    fixtures = [fixture for fixture in build_corpus(target_size=10) if fixture.get("force_pass3")]
    elapsed: list[float] = []
    savings_pct: list[float] = []
    quality: list[float] = []

    for iteration in range(iterations):
        for fixture in fixtures:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config = SessionSiftConfig(
                    registry_path=str(Path(tmp_dir) / f"{fixture['name']}-{iteration}.db"),
                    pass3_enabled=True,
                    pass3_provider=candidate["provider"],
                    pass3_model=candidate["model"],
                    pass3_api_key_env=candidate["env_var"],
                    pass3_base_url=candidate["base_url"],
                    **fixture.get("config", {}),
                )
                engine = SessionSiftEngine(config)
                start = time.perf_counter()
                refined, report = await engine.refine(fixture["messages"], force_pass3=True)
                elapsed.append((time.perf_counter() - start) * 1000)
                savings_pct.append(report.savings_pct)
                quality.append(preservation_score(fixture["expectations"], refined))

    avg_elapsed = sum(elapsed) / max(len(elapsed), 1)
    avg_savings = sum(savings_pct) / max(len(savings_pct), 1)
    avg_quality = sum(quality) / max(len(quality), 1)
    estimated_cost_per_1k_turns = (avg_savings / 100) * 3.0
    return {
        "provider": candidate["provider"],
        "model": candidate["model"],
        "status": "ok",
        "iterations": iterations,
        "fixtures": len(fixtures),
        "avg_elapsed_ms": round(avg_elapsed, 3),
        "avg_savings_pct": round(avg_savings, 3),
        "avg_preservation_score": round(avg_quality, 3),
        "estimated_cost_saved_usd_per_1k_turns": round(estimated_cost_per_1k_turns, 4),
    }


async def main(candidates: list[dict], iterations: int) -> None:
    results = [await run_candidate(candidate, iterations) for candidate in candidates]
    print(json.dumps({"candidates": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Pass 3 candidate models across the semantic session corpus.")
    parser.add_argument(
        "--candidate",
        action="append",
        required=False,
        help="provider|model|ENV_VAR|base_url",
    )
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    candidates = [
        parse_candidate(value)
        for value in (args.candidate or [
            "anthropic|claude-haiku-3-5|ANTHROPIC_API_KEY|https://api.anthropic.com",
            "openai|gpt-4o-mini|OPENAI_API_KEY|https://api.openai.com",
        ])
    ]
    asyncio.run(main(candidates, args.iterations))