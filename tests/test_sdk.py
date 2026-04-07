from pathlib import Path

import pytest

from session_sift.config import SessionSiftConfig
from session_sift.sdk import SessionSiftSDK


@pytest.mark.asyncio
async def test_sdk_refine_and_dna_roundtrip(tmp_path: Path) -> None:
    config = SessionSiftConfig(registry_path=str(tmp_path / "registry.db"), dna_path=str(tmp_path / "dna.json"))
    sdk = SessionSiftSDK(config)

    refined, report = await sdk.refine([{"role": "user", "content": f"hello {i}"} for i in range(10)])
    exported = await sdk.export_dna()
    imported = await sdk.import_dna(str(tmp_path / "dna.json"))

    assert len(refined) == 10
    assert report.turn == 1
    assert exported["session_id"]
    assert imported["imported_files"] >= 0


def test_sdk_create_proxy_app() -> None:
    sdk = SessionSiftSDK(SessionSiftConfig())
    app = sdk.create_proxy_app()
    assert app is not None