from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


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


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_title: str
    version: str
    cors_allow_origins: tuple[str, ...]
    top_cache_ttl_seconds: int
    history_cache_ttl_seconds: int
    rate_limit_window_seconds: int
    rate_limit_max_requests_stat: int
    rate_limit_max_requests_ai: int
    openai_chat_completions_url: str
    openai_model: str
    openai_api_key: str
    stock_llm_api_url: str
    stock_llm_api_key: str
    redis_url: str
    redis_prefix: str
    redis_socket_timeout_seconds: float
    trusted_proxy_ips: tuple[str, ...]

    @property
    def use_trusted_proxy_headers(self) -> bool:
        return bool(self.trusted_proxy_ips)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    cors_origins = _csv_env("CORS_ALLOW_ORIGINS")
    if not cors_origins:
        cors_origins = (
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        )

    return Settings(
        app_title="Stock & Crypto Predictor API",
        version="0.5.0",
        cors_allow_origins=cors_origins,
        top_cache_ttl_seconds=_int_env("TOP_CACHE_TTL_SECONDS", 15 * 60, minimum=30),
        history_cache_ttl_seconds=_int_env("HISTORY_CACHE_TTL_SECONDS", 5 * 60, minimum=30),
        rate_limit_window_seconds=_int_env("RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1),
        rate_limit_max_requests_stat=_int_env("RATE_LIMIT_MAX_REQUESTS_STAT", 30, minimum=0),
        rate_limit_max_requests_ai=_int_env("RATE_LIMIT_MAX_REQUESTS_AI", 8, minimum=0),
        openai_chat_completions_url=os.getenv(
            "OPENAI_CHAT_COMPLETIONS_URL",
            "https://api.openai.com/v1/chat/completions",
        ).strip()
        or "https://api.openai.com/v1/chat/completions",
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        stock_llm_api_url=os.getenv("STOCK_LLM_API_URL", "").strip(),
        stock_llm_api_key=os.getenv("STOCK_LLM_API_KEY", "").strip(),
        redis_url=os.getenv("REDIS_URL", "").strip(),
        redis_prefix=os.getenv("REDIS_PREFIX", "stock-predictor").strip() or "stock-predictor",
        redis_socket_timeout_seconds=_float_env("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0, minimum=0.1),
        trusted_proxy_ips=_csv_env("TRUSTED_PROXY_IPS"),
    )
