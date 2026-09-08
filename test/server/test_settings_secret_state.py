from __future__ import annotations

import json
from pathlib import Path

from server.routes import settings


def _point_settings_to(path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "CONFIG_PATH", path)


def test_safe_settings_uses_env_key_length_without_exposing_secret(
    tmp_path: Path, monkeypatch
) -> None:
    _point_settings_to(tmp_path / "settings.json", monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdefghijklmnopqrstuvwxyz123456")

    response = settings._safe_settings(settings._load_settings())

    assert response["llm_api_key"] == "*" * 35
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(response)
    assert response["llm_api_key_configured"] is True
    assert response["llm_api_key_source"] == "properties.env"
    assert response["llm_api_key_length"] == 35


def test_safe_settings_prefers_saved_key_over_env_key(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps({"llm_api_key": "sk-saved-secret"}),
        encoding="utf-8",
    )
    _point_settings_to(config_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret")

    response = settings._safe_settings(settings._load_settings())

    assert response["llm_api_key"] == "*" * len("sk-saved-secret")
    assert response["llm_api_key_source"] == "settings"
    assert response["llm_api_key_length"] == len("sk-saved-secret")


def test_update_settings_preserves_raw_key_when_length_mask_is_posted(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps({"llm_api_key": "sk-saved-secret"}),
        encoding="utf-8",
    )
    _point_settings_to(config_path, monkeypatch)

    settings._save_settings(
        settings._merge_settings_update(
            settings._load_settings(),
            {"llm_api_key": "*" * len("sk-saved-secret"), "memory_enabled": False},
        )
    )

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm_api_key"] == "sk-saved-secret"
    assert saved["memory_enabled"] is False


def test_update_settings_does_not_copy_env_secret_when_mask_is_posted(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "settings.json"
    _point_settings_to(config_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-only-secret")

    settings._save_settings(
        settings._merge_settings_update(
            settings._load_settings(),
            {"llm_api_key": "*" * len("sk-env-only-secret")},
        )
    )

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm_api_key"] == ""
