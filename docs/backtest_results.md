# Aurion Backtest Results

Generated: 2026-04-06 16:12 UTC

**Configuration**: horizon=30 days, folds=5

## Results

| Ticker | Type | Rows | ML MAE | ML MAPE% | ML Dir.Acc | Stat MAPE% | Stat Dir.Acc | ML Beats Stat | Notes |
|--------|------|------|--------|----------|------------|------------|--------------|---------------|-------|
| AAPL | stock | 500 | 13.25 | 5.81 | 0.5172 | 11.14 | 0.5448 | YES |  |
| MSFT | stock | 500 | 17.86 | 4.14 | 0.5241 | 11.93 | 0.5103 | YES |  |
| GOOG | stock | 500 | 13.85 | 5.32 | 0.5241 | 13.00 | 0.4345 | YES |  |
| TSLA | stock | 500 | 80.60 | 20.82 | 0.5310 | 29.37 | 0.5172 | YES |  |
| AMZN | stock | 500 | 12.06 | 5.53 | 0.4483 | 10.11 | 0.4483 | YES |  |
| NVDA | stock | 500 | 9.86 | 6.78 | 0.5379 | 15.31 | 0.5103 | YES |  |
| BTC-USD | crypto | 731 | 5717.47 | 6.43 | 0.5379 | 24.33 | 0.4966 | YES |  |
| ETH-USD | crypto | 731 | 481.39 | 14.06 | 0.4207 | 22.37 | 0.4069 | YES |  |

## Summary

- **Tickers evaluated**: 8
- **ML models trained**: 8
- **ML wins (lower MAPE)**: 8
- **Stat wins**: 0
- **Avg ML MAPE**: 8.61%
- **Avg Stat MAPE**: 17.20%
- **Avg ML Directional Accuracy**: 0.5051

## Notes

- **ML MAE**: Mean Absolute Error of the ML analog forecaster
- **MAPE**: Mean Absolute Percentage Error (lower is better)
- **Dir.Acc**: Directional accuracy -- fraction of days where predicted direction matched actual
- **ML Beats Stat**: Whether the ML model achieved lower MAPE than the statistical baseline
- Statistical baseline uses log-linear trend extrapolation with cross-validation
- ML model uses k-nearest-neighbor analog pattern matching
