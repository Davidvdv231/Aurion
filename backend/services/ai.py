from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import pandas as pd

from backend.config import Settings
from backend.errors import ServiceError
from backend.services.forecast import normalize_ai_forecast_rows
from backend.ticker_catalog import AssetType

logger = logging.getLogger("stock_predictor.ai")


def _extract_json_payload(text: str, provider: str) -> dict:
    payload_text = text.strip()
    if payload_text.startswith("```"):
        payload_text = payload_text.strip("`")
        if payload_text.startswith("json"):
            payload_text = payload_text[4:]
        payload_text = payload_text.strip()

    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="AI model response was not valid JSON.",
            provider=provider,
            retryable=True,
        ) from exc

    if not isinstance(parsed, dict):
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="AI model response must be a JSON object.",
            provider=provider,
            retryable=True,
        )

    return parsed


def _build_external_ai_forecast(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    settings: Settings,
) -> tuple[list[dict], dict]:
    history_window = close.tail(220)
    payload = {
        "symbol": symbol,
        "asset_type": asset_type,
        "horizon_days": horizon,
        "history": [
            {"date": idx.date().isoformat(), "close": round(float(price), 4)}
            for idx, price in history_window.items()
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.stock_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.stock_llm_api_key}"

    request = UrlRequest(
        settings.stock_llm_api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=25) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:200]
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message=f"External AI returned HTTP {exc.code}: {detail or 'no detail'}",
            provider="external_ai",
            retryable=True,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="External AI service unreachable.",
            provider="external_ai",
            retryable=True,
        ) from exc

    parsed = _extract_json_payload(response_body, provider="external_ai")
    forecast_rows = parsed.get("forecast")
    if not isinstance(forecast_rows, list):
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="External AI response must contain a forecast list.",
            provider="external_ai",
            retryable=True,
        )

    normalized_forecast = normalize_ai_forecast_rows(
        forecast_rows=forecast_rows,
        close=close,
        horizon=horizon,
        asset_type=asset_type,
        provider="external_ai",
    )

    model_info = {
        "provider": str(parsed.get("provider", "external_ai")),
        "model": str(parsed.get("model", "custom-stock-llm")),
        "source": "external_ai",
    }
    return normalized_forecast, model_info


def _build_openai_forecast(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    settings: Settings,
) -> tuple[list[dict], dict]:
    history_window = close.tail(200 if asset_type == "stock" else 240)
    history_payload = [
        {"date": idx.date().isoformat(), "close": round(float(price), 4)}
        for idx, price in history_window.items()
    ]
    calendar_hint = "trading days" if asset_type == "stock" else "calendar days"

    payload = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a quantitative market forecaster. Return strict JSON only. "
                    "No markdown, no commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create a {horizon}-step forecast for {symbol} ({asset_type}). "
                    f"Use {calendar_hint} from the last history date. "
                    "Return JSON object with key 'forecast' as an array of objects with: "
                    "date (YYYY-MM-DD), predicted (number), lower (number), upper (number). "
                    "History JSON follows:\n"
                    f"{json.dumps(history_payload, separators=(',', ':'))}"
                ),
            },
        ],
    }

    request = UrlRequest(
        settings.openai_chat_completions_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.openai_api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:220]
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message=f"OpenAI returned HTTP {exc.code}: {detail or 'no detail'}",
            provider="openai",
            retryable=True,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="OpenAI service unreachable.",
            provider="openai",
            retryable=True,
        ) from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="OpenAI response was not valid JSON.",
            provider="openai",
            retryable=True,
        ) from exc

    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="OpenAI response contains no choices.",
            provider="openai",
            retryable=True,
        )

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        content = "".join(parts)

    if not isinstance(content, str) or not content.strip():
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="OpenAI returned no usable content.",
            provider="openai",
            retryable=True,
        )

    model_payload = _extract_json_payload(content, provider="openai")
    forecast_rows = model_payload.get("forecast")
    if not isinstance(forecast_rows, list):
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="OpenAI response must contain a forecast list.",
            provider="openai",
            retryable=True,
        )

    normalized_forecast = normalize_ai_forecast_rows(
        forecast_rows=forecast_rows,
        close=close,
        horizon=horizon,
        asset_type=asset_type,
        provider="openai",
    )

    model_info = {
        "provider": "openai",
        "model": str(parsed.get("model", settings.openai_model)),
        "source": "openai",
    }
    return normalized_forecast, model_info


def build_ai_forecast(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    settings: Settings,
) -> tuple[list[dict], dict]:
    if settings.stock_llm_api_url:
        return _build_external_ai_forecast(
            symbol=symbol,
            close=close,
            horizon=horizon,
            asset_type=asset_type,
            settings=settings,
        )

    if settings.openai_api_key:
        return _build_openai_forecast(
            symbol=symbol,
            close=close,
            horizon=horizon,
            asset_type=asset_type,
            settings=settings,
        )

    logger.info("AI forecast requested but no AI provider is configured")
    raise ServiceError(
        status_code=400,
        code="not_configured",
        message="AI engine not configured. Set OPENAI_API_KEY or STOCK_LLM_API_URL.",
        provider="ai",
        retryable=False,
    )
