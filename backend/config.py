from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return

    preexisting_keys = set(os.environ.keys())

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in preexisting_keys:
            continue

        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()

        os.environ[key] = value


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return max(minimum, default)

    try:
        value = int(raw)
    except ValueError:
        return max(minimum, default)

    return max(minimum, value)


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return max(minimum, default)

    try:
        value = float(raw)
    except ValueError:
        return max(minimum, default)

    return max(minimum, value)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    app_title: str
    version: str
    cors_allow_origins: tuple[str, ...]
    top_cache_ttl_seconds: int
    history_cache_ttl_seconds: int
    blocking_task_timeout_seconds: float
    top_assets_timeout_seconds: float
    executor_max_workers: int
    memory_cache_max_items: int
    memory_cache_sweep_batch_size: int
    rate_limit_window_seconds: int
    rate_limit_max_requests_stat: int
    rate_limit_max_requests_ai: int
    rate_limit_max_requests_search: int
    rate_limit_fail_open: bool
    openai_chat_completions_url: str
    openai_model: str
    openai_api_key: str
    stock_llm_api_url: str
    stock_llm_api_key: str
    redis_url: str
    redis_prefix: str
    redis_socket_timeout_seconds: float
    trusted_proxy_ips: tuple[str, ...]
    ml_min_validation_windows: int
    ml_min_directional_accuracy: float
    ml_max_mape_vs_baseline: float

    @property
    def use_trusted_proxy_headers(self) -> bool:
        return bool(self.trusted_proxy_ips)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_local_env()
    app_env = os.getenv("APP_ENV", "development").strip() or "development"

    cors_origins = _csv_env("CORS_ALLOW_ORIGINS")
    if not cors_origins:
        cors_origins = (
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        )

    return Settings(
        app_env=app_env,
        app_title="Aurion - AI Market Intelligence API",
        version="0.5.0",
        cors_allow_origins=cors_origins,
        top_cache_ttl_seconds=_int_env("TOP_CACHE_TTL_SECONDS", 15 * 60, minimum=30),
        history_cache_ttl_seconds=_int_env("HISTORY_CACHE_TTL_SECONDS", 5 * 60, minimum=30),
        blocking_task_timeout_seconds=_float_env(
            "BLOCKING_TASK_TIMEOUT_SECONDS", 15.0, minimum=1.0
        ),
        top_assets_timeout_seconds=_float_env("TOP_ASSETS_TIMEOUT_SECONDS", 8.0, minimum=1.0),
        executor_max_workers=_int_env("EXECUTOR_MAX_WORKERS", 8, minimum=1),
        memory_cache_max_items=_int_env("MEMORY_CACHE_MAX_ITEMS", 512, minimum=32),
        memory_cache_sweep_batch_size=_int_env("MEMORY_CACHE_SWEEP_BATCH_SIZE", 64, minimum=1),
        rate_limit_window_seconds=_int_env("RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1),
        rate_limit_max_requests_stat=_int_env("RATE_LIMIT_MAX_REQUESTS_STAT", 30, minimum=0),
        rate_limit_max_requests_ai=_int_env("RATE_LIMIT_MAX_REQUESTS_AI", 8, minimum=0),
        rate_limit_max_requests_search=_int_env("RATE_LIMIT_MAX_REQUESTS_SEARCH", 60, minimum=0),
        rate_limit_fail_open=_bool_env(
            "RATE_LIMIT_FAIL_OPEN",
            default=app_env.lower() not in {"prod", "production"},
        ),
        openai_chat_completions_url=os.getenv(
            "OPENAI_CHAT_COMPLETIONS_URL",
            "https://api.openai.com/v1/chat/completions",
        ).strip()
        or "https://api.openai.com/v1/chat/completions",
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        stock_llm_api_url=os.getenv("STOCK_LLM_API_URL", "").strip(),
        stock_llm_api_key=os.getenv("STOCK_LLM_API_KEY", "").strip(),
        redis_url=os.getenv("REDIS_URL", "").strip(),
        redis_prefix=os.getenv("REDIS_PREFIX", "stock-predictor").strip() or "stock-predictor",
        redis_socket_timeout_seconds=_float_env("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0, minimum=0.1),
        trusted_proxy_ips=_csv_env("TRUSTED_PROXY_IPS"),
        ml_min_validation_windows=_int_env("ML_MIN_VALIDATION_WINDOWS", 3, minimum=1),
        ml_min_directional_accuracy=_float_env("ML_MIN_DIRECTIONAL_ACCURACY", 0.45, minimum=0.0),
        ml_max_mape_vs_baseline=_float_env("ML_MAX_MAPE_VS_BASELINE", 1.0, minimum=0.0),
    )
