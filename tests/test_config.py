from pathlib import Path

from session_sift.config import SessionSiftConfig


def test_config_save_and_load(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = SessionSiftConfig(decay_lambda=0.08, strict_protected=["STRICT", "TODO"])
    path = config.save()

    loaded = SessionSiftConfig.load(str(path))

    assert loaded.decay_lambda == 0.08
    assert loaded.strict_protected == ["STRICT", "TODO"]


def test_config_coerce_value_types() -> None:
    assert SessionSiftConfig.coerce_value("decay_lambda", "0.12") == 0.12
    assert SessionSiftConfig.coerce_value("token_threshold", "42") == 42
    assert SessionSiftConfig.coerce_value("pass3_enabled", "true") is True
    assert SessionSiftConfig.coerce_value("strict_protected", "A,B") == ["A", "B"]


def test_config_resolve_paths_and_load_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = SessionSiftConfig()

    assert config.resolve_registry_path() == tmp_path / ".session-sift/registry.db"
    assert config.resolve_dna_path() == tmp_path / ".session-sift/dna.json"
    assert config.resolve_config_path() == tmp_path / ".session-sift/config.json"
    assert SessionSiftConfig.load().config_path == ".session-sift/config.json"


def test_config_load_filters_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"token_threshold": 99, "unknown": true}', encoding="utf-8")

    loaded = SessionSiftConfig.load(str(path))

    assert loaded.token_threshold == 99
    assert not hasattr(loaded, "unknown")