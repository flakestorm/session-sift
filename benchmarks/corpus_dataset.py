from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "sessions"


def load_seed_fixtures() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]


def build_corpus(target_size: int = 50) -> list[dict]:
    seeds = load_seed_fixtures()
    if not seeds:
        return []

    corpus: list[dict] = []
    variant = 0
    while len(corpus) < target_size:
        seed = seeds[len(corpus) % len(seeds)]
        corpus.append(_variant_fixture(seed, variant))
        variant += 1
    return corpus


def _variant_fixture(seed: dict, variant: int) -> dict:
    fixture = copy.deepcopy(seed)
    fixture["name"] = f"{seed['name']}_{variant:02d}"
    fixture["description"] = f"{seed.get('description', '').strip()} Variant {variant}."
    salt = variant + 1
    fixture["messages"] = [_variant_message(message, salt) for message in fixture["messages"]]
    return fixture


def _variant_message(message: dict, salt: int) -> dict:
    updated = copy.deepcopy(message)
    content = updated.get("content")
    if isinstance(content, str):
        updated["content"] = _variant_text(content, salt)
    elif isinstance(content, list):
        updated["content"] = [_variant_block(block, salt) for block in content]
    return updated


def _variant_block(block: object, salt: int) -> object:
    if not isinstance(block, dict):
        return block
    updated = copy.deepcopy(block)
    if isinstance(updated.get("input"), dict):
        updated["input"] = {
            key: _variant_nested(value, salt)
            for key, value in updated["input"].items()
        }
    if isinstance(updated.get("content"), str):
        updated["content"] = _variant_text(updated["content"], salt)
    return updated


def _variant_nested(value: object, salt: int) -> object:
    if isinstance(value, str):
        return _variant_text(value, salt)
    if isinstance(value, list):
        return [_variant_nested(item, salt) for item in value]
    if isinstance(value, dict):
        return {key: _variant_nested(inner, salt) for key, inner in value.items()}
    return value


def _variant_text(text: str, salt: int) -> str:
    replacements = {
        "./src/app.py": f"./src/app_{salt}.py",
        "./session_sift/server_proxy.py": f"./session_sift/server_proxy_{salt}.py",
        "session_sift/server_proxy.py": f"session_sift/server_proxy_{salt}.py",
        "session_sift/engine.py": f"session_sift/engine_{salt}.py",
        "tests/test_proxy.py": f"tests/test_proxy_{salt}.py",
        "error 500": f"error {500 + salt}",
        " 500 ": f" {500 + salt} ",
        "Resolved.": f"Resolved variant {salt}.",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result