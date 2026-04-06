from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from backend.config import get_settings

TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp" / "pytest-config"


def _make_temp_root() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_root = TMP_ROOT / f"case-{uuid.uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=False)
    return temp_root


def test_get_settings_loads_values_from_dotenv(monkeypatch) -> None:
    temp_root = _make_temp_root()
    try:
        (temp_root / ".env").write_text(
            "REDIS_PREFIX=test-prefix\nCORS_ALLOW_ORIGINS=http://a,http://b\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("backend.config.PROJECT_ROOT", temp_root)

        settings = get_settings()

        assert settings.redis_prefix == "test-prefix"
        assert settings.cors_allow_origins == ("http://a", "http://b")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_real_environment_overrides_dotenv(monkeypatch) -> None:
    temp_root = _make_temp_root()
    try:
        (temp_root / ".env").write_text("REDIS_PREFIX=dotenv-value\n", encoding="utf-8")
        monkeypatch.setattr("backend.config.PROJECT_ROOT", temp_root)
        monkeypatch.setenv("REDIS_PREFIX", "shell-value")

        settings = get_settings()

        assert settings.redis_prefix == "shell-value"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_rate_limit_fail_open_defaults_to_environment_mode(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    assert get_settings().rate_limit_fail_open is True

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    assert get_settings().rate_limit_fail_open is False


def test_rate_limit_fail_open_can_be_disabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "false")

    settings = get_settings()

    assert settings.rate_limit_fail_open is False
