export type AssetType = "stock" | "crypto";
export type ForecastEngine = "stat" | "ml" | "ai";
export type EngineUsed = "stat" | "ml" | "ai" | "stat_fallback" | "ml_fallback";
export type PredictionTrend = "bullish" | "bearish" | "neutral";
export type ConfidenceTier = "low" | "medium" | "high";
export type PredictionSignal = "bullish" | "mildly_bullish" | "neutral" | "mildly_bearish" | "bearish";

export interface TickerItem {
  symbol: string;
  name: string;
  exchange: string;
  region: string;
  popularity: number;
  asset_type: AssetType;
  score?: number | null;
  source?: string | null;
}

export interface TickerSearchResponse {
  query: string;
  asset_type: AssetType;
  tickers: TickerItem[];
}

export interface TopAssetsResponse {
  generated_at: string;
  asset_type: AssetType;
  source: string;
  items: TickerItem[];
}

export interface HistoryPoint {
  date: string;
  close: number;
}

export interface ForecastPoint {
  date: string;
  predicted: number;
  lower: number;
  upper: number;
}

export interface PredictStats {
  daily_trend_pct: number;
  last_close: number;
}

export interface PredictionSummary {
  expected_price: number;
  expected_return_pct: number;
  trend: PredictionTrend;
  confidence_tier: ConfidenceTier;
  probability_up: number;
  signal: PredictionSignal;
}

export interface PredictionEvaluation {
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  directional_accuracy: number | null;
  validation_windows: number | null;
}

export interface PredictionSource {
  market_data: string;
  forecast: string;
}

export interface PredictResponse {
  symbol: string;
  requested_symbol: string;
  asset_type: AssetType;
  currency: string;
  generated_at: string;
  horizon_days: number;
  engine_requested: ForecastEngine;
  engine_used: EngineUsed;
  model_name: string;
  engine_note: string;
  source: PredictionSource;
  degraded: boolean;
  degradation_code: string | null;
  degradation_message: string | null;
  degradation_reason: string | null;
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  stats: PredictStats;
  summary: PredictionSummary;
  evaluation: PredictionEvaluation | null;
  disclaimer: string;
}
