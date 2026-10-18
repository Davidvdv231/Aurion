# Aurion Backtest Results

Generated: 2026-10-18 11:25 UTC

**Configuration**: horizon=30 days, folds=5

## Results

| Ticker | Type | Rows | ML MAE | ML MAPE% | ML Dir.Acc | Stat MAPE% | Stat Dir.Acc | ML Beats Stat | Notes |
|--------|------|------|--------|----------|------------|------------|--------------|---------------|-------|
| AAPL | stock | 501 | 11.29 | 4.36 | 0.5167 | 4.40 | 0.7000 | YES |  |
| MSFT | stock | 501 | 22.36 | 4.88 | 0.5167 | 4.99 | 0.3800 | YES |  |
| GOOG | stock | 501 | 25.85 | 8.45 | 0.5067 | 3.88 | 0.4933 | no |  |
| TSLA | stock | 501 | 19.55 | 5.01 | 0.4133 | 6.13 | 0.3867 | YES |  |
| AMZN | stock | 501 | 10.88 | 4.61 | 0.4400 | 5.10 | 0.2000 | YES |  |
| NVDA | stock | 501 | 10.96 | 5.65 | 0.4600 | 3.32 | 0.5467 | no |  |
| BTC-USD | crypto | 731 | 6684.85 | 9.05 | 0.5500 | 6.57 | 0.6133 | no |  |
| ETH-USD | crypto | 731 | 291.28 | 13.21 | 0.4900 | 11.56 | 0.4067 | no |  |

## Summary

- **Tickers evaluated**: 8
- **ML models trained**: 8
- **ML wins (lower MAPE)**: 4
- **Stat wins**: 4
- **Avg ML MAPE**: 6.90%
- **Avg Stat MAPE**: 5.74%
- **Avg ML Directional Accuracy**: 0.4867

## Notes

- **ML MAE**: Mean Absolute Error of the ML analog forecaster
- **MAPE**: Mean Absolute Percentage Error (lower is better)
- **Dir.Acc**: Directional accuracy -- share of forecast days where the forecast was on the correct side of the starting price (a flat forecast counts as half)
- **ML Beats Stat**: Whether the ML model achieved lower MAPE than the statistical baseline
- Statistical baseline uses a damped log-linear trend anchored at the last close, with volatility bands
- ML model uses k-nearest-neighbor analog pattern matching
- Each ticker is scored on only 5 thirty-day windows (the backtest the quality gate uses), so per-ticker numbers are noisy; `scripts/evaluate_forecasts.py` runs a larger walk-forward evaluation
