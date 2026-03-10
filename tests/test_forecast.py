from __future__ import annotations

import pandas as pd
import pytest

from backend.errors import ServiceError
from backend.services.forecast import normalize_ai_forecast_rows


def _close_series() -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=120)
    values = pd.Series(range(100, 220), index=index, dtype=float)
    return values


def test_normalize_ai_forecast_rows_rejects_invalid_dates() -> None:
    with pytest.raises(ServiceError) as exc_info:
        normalize_ai_forecast_rows(
            forecast_rows=[
                {"date": "not-a-date", "predicted": 150},
                {"date": "2025-04-02", "predicted": 151},
            ],
            close=_close_series(),
            horizon=2,
            asset_type="stock",
            provider="openai",
        )

    assert exc_info.value.code == "provider_invalid_response"


def test_normalize_ai_forecast_rows_generates_bands_when_missing() -> None:
    result = normalize_ai_forecast_rows(
        forecast_rows=[
            {"date": "2025-04-01", "predicted": 150},
            {"date": "2025-04-02", "predicted": 151},
        ],
        close=_close_series(),
        horizon=2,
        asset_type="stock",
        provider="openai",
    )

    assert len(result) == 2
    assert result[0]["lower"] > 0
    assert result[0]["upper"] > result[0]["lower"]
