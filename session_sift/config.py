from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_type_hints

from session_sift.utils import ensure_parent_dir


@dataclass(slots=True)
class SessionSiftConfig:
    token_threshold: int = 50_000
    max_context_tokens: int = 128_000
    pass3_model: str = "claude-haiku-3-5"
    pass3_enabled: bool = False
    strict_protected: list[str] = field(
        default_factory=lambda: ["STRICT", "TODO", "FIXME"]
    )
    decay_lambda: float = 0.05
    decay_recency_boost: float = 3.0
    recency_window: int = 5
    pruning_threshold: float = 0.15
    pass3_timeout_secs: float = 5.0
    pass3_target_ratio: float = 0.30
    pass3_provider: str = "anthropic"
    pass3_base_url: str = "https://api.anthropic.com"
    pass3_api_key_env: str = "ANTHROPIC_API_KEY"
    registry_path: str = ".session-sift/registry.db"
    dna_path: str = ".session-sift/dna.json"
    config_path: str = ".session-sift/config.json"
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 9978
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 9977
    upstream_provider: str = "openai"
    upstream_url: str = "https://api.openai.com"
    request_timeout_secs: float = 60.0

    def resolve_registry_path(self, root: Path | None = None) -> Path:
        base = root or Path.cwd()
        return base / self.registry_path

    def resolve_dna_path(self, root: Path | None = None) -> Path:
        base = root or Path.cwd()
        return base / self.dna_path

    def resolve_config_path(self, root: Path | None = None) -> Path:
        base = root or Path.cwd()
        return base / self.config_path

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: str | None = None) -> "SessionSiftConfig":
        config = cls()
        config_path = Path(path) if path else config.resolve_config_path()
        if not config_path.exists():
            return config
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        valid = {field_info.name for field_info in fields(cls)}
        overrides = {key: value for key, value in payload.items() if key in valid}
        return cls(**overrides)

    def save(self, path: str | None = None) -> Path:
        config_path = Path(path) if path else self.resolve_config_path()
        ensure_parent_dir(str(config_path))
        config_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return config_path

    @classmethod
    def coerce_value(cls, key: str, raw: str):
        field_map = get_type_hints(cls)
        target = field_map[key]
        if target is int:
            return int(raw)
        if target is float:
            return float(raw)
        if target is bool:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        if str(target).startswith("list"):
            return [part.strip() for part in raw.split(",") if part.strip()]
        return raw
