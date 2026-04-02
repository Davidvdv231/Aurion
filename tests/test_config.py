from __future__ import annotations

from pathlib import Path
import shutil
import uuid

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
            "OPENAI_API_KEY=test-openai-key\nOPENAI_MODEL=test-model\nCORS_ALLOW_ORIGINS=http://a,http://b\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("backend.config.PROJECT_ROOT", temp_root)
        monkeypatch.delenv("STOCK_PREDICTOR_DISABLE_DOTENV", raising=False)

        settings = get_settings()

        assert settings.openai_api_key == "test-openai-key"
        assert settings.openai_model == "test-model"
        assert settings.cors_allow_origins == ("http://a", "http://b")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_real_environment_overrides_dotenv(monkeypatch) -> None:
    temp_root = _make_temp_root()
    try:
        (temp_root / ".env").write_text("OPENAI_API_KEY=dotenv-value\n", encoding="utf-8")
        monkeypatch.setattr("backend.config.PROJECT_ROOT", temp_root)
        monkeypatch.delenv("STOCK_PREDICTOR_DISABLE_DOTENV", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "shell-value")

        settings = get_settings()

        assert settings.openai_api_key == "shell-value"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_placeholder_secret_values_are_treated_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "HIER_JE_OPENAI_KEY")
    monkeypatch.setenv("STOCK_LLM_API_KEY", "YOUR_ENDPOINT_KEY")

    settings = get_settings()

    assert settings.openai_api_key == ""
    assert settings.stock_llm_api_key == ""


def test_dotenv_loading_can_be_disabled_for_tests(monkeypatch) -> None:
    temp_root = _make_temp_root()
    try:
        (temp_root / ".env").write_text("OPENAI_API_KEY=dotenv-value\n", encoding="utf-8")
        monkeypatch.setattr("backend.config.PROJECT_ROOT", temp_root)
        monkeypatch.setenv("STOCK_PREDICTOR_DISABLE_DOTENV", "1")

        settings = get_settings()

        assert settings.openai_api_key == ""
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
