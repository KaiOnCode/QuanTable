from __future__ import annotations

import json
from pathlib import Path

from server.routes import settings


def _point_settings_to(path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "CONFIG_PATH", path)


def test_settings_defaults_use_deepseek_v4_models(tmp_path: Path, monkeypatch) -> None:
    _point_settings_to(tmp_path / "settings.json", monkeypatch)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    loaded = settings._load_settings()

    assert loaded["llm_model"] == "deepseek-v4-flash"
    assert loaded["deep_think_model"] == "deepseek-v4-pro"


def test_settings_load_migrates_legacy_deepseek_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "llm_model": "deepseek-chat",
                "deep_think_model": "deepseek-reasoning",
            }
        ),
        encoding="utf-8",
    )
    _point_settings_to(config_path, monkeypatch)

    loaded = settings._load_settings()

    assert loaded["llm_model"] == "deepseek-v4-flash"
    assert loaded["deep_think_model"] == "deepseek-v4-pro"


def test_settings_preserves_non_deepseek_models(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "llm_model": "gpt-4o-mini",
                "deep_think_model": "claude-sonnet-4-6",
            }
        ),
        encoding="utf-8",
    )
    _point_settings_to(config_path, monkeypatch)

    loaded = settings._load_settings()

    assert loaded["llm_model"] == "gpt-4o-mini"
    assert loaded["deep_think_model"] == "claude-sonnet-4-6"
