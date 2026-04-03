from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.config import get_settings

APP_ENV_VARS = [
    "APP_ENV",
    "ARTIFACTS_ROOT",
    "BLOCKING_TASK_TIMEOUT_SECONDS",
    "CORS_ALLOW_ORIGINS",
    "EXECUTOR_MAX_WORKERS",
    "HISTORY_CACHE_TTL_SECONDS",
    "MEMORY_CACHE_MAX_ITEMS",
    "MEMORY_CACHE_SWEEP_BATCH_SIZE",
    "ML_BACKTEST_WINDOWS",
    "ML_MIN_HISTORY_ROWS",
    "ML_NEIGHBOR_COUNT",
    "OPENAI_API_KEY",
    "OPENAI_CHAT_COMPLETIONS_URL",
    "OPENAI_MODEL",
    "REDIS_URL",
    "REDIS_PREFIX",
    "REDIS_SOCKET_TIMEOUT_SECONDS",
    "RATE_LIMIT_MAX_REQUESTS_SEARCH",
    "RATE_LIMIT_FAIL_OPEN",
    "STOCK_LLM_API_KEY",
    "STOCK_LLM_API_URL",
    "TOP_CACHE_TTL_SECONDS",
    "TOP_ASSETS_TIMEOUT_SECONDS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "RATE_LIMIT_MAX_REQUESTS_STAT",
    "RATE_LIMIT_MAX_REQUESTS_AI",
    "TRUSTED_PROXY_IPS",
]


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    originals = {name: os.environ.get(name) for name in APP_ENV_VARS}
    for name in APP_ENV_VARS:
        os.environ.pop(name, None)

    yield

    get_settings.cache_clear()
    for name in APP_ENV_VARS:
        os.environ.pop(name, None)
    for name, value in originals.items():
        if value is not None:
            os.environ[name] = value


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
