from __future__ import annotations

from aiohttp import web

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.server_proxy import create_app


class SessionSiftSDK:
    def __init__(self, config: SessionSiftConfig | None = None) -> None:
        self.config = config or SessionSiftConfig()
        self.engine = SessionSiftEngine(self.config)

    async def refine(self, messages: list[dict], force_pass3: bool = False):
        return await self.engine.refine(messages, force_pass3=force_pass3)

    async def export_dna(self, output_path: str | None = None) -> dict:
        return await self.engine.export_dna(output_path or self.config.dna_path)

    async def import_dna(self, input_path: str) -> dict:
        return await self.engine.import_dna(input_path)

    def create_proxy_app(self) -> web.Application:
        return create_app(self.config, self.engine)
