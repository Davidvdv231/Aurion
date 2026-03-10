from __future__ import annotations

from backend.services.market_data import candidate_symbols, infer_currency


def test_candidate_symbols_prioritizes_stock_aliases() -> None:
    candidates = candidate_symbols("KBC", "stock")

    assert candidates[0] == "KBC.BR"
    assert "KBC" in candidates


def test_candidate_symbols_expands_crypto_inputs() -> None:
    candidates = candidate_symbols("BTC", "crypto")

    assert candidates[0] == "BTC-USD"
    assert "BTC-USD" in candidates


def test_infer_currency_uses_market_suffix() -> None:
    assert infer_currency("KBC.BR", "stock") == "EUR"
    assert infer_currency("AAPL", "stock") == "USD"
    assert infer_currency("BTC-USD", "crypto") == "USD"
