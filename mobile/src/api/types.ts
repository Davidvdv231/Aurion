export type AssetType = "stock" | "crypto";
export type ForecastEngine = "stat" | "ml";
export type EngineUsed = "stat" | "ml" | "stat_fallback";
export type PredictionTrend = "bullish" | "bearish" | "neutral";
export type ConfidenceTier = "low" | "medium" | "high";
export type PredictionSignal = "Strongly Bullish" | "Bullish Outlook" | "Neutral" | "Bearish Outlook" | "Strongly Bearish";

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
  signal: PredictionSignal;
}

export interface PredictionEvaluation {
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  directional_accuracy: number | null;
  validation_windows: number | null;
}

export interface ExplanationFeature {
  feature: string;
  difference_score: number;
  value: number;
  relation: "higher" | "lower" | "similar";
}

export interface PredictionExplanation {
  top_features: ExplanationFeature[];
  neighbors_used: number;
  avg_neighbor_distance: number;
  nearest_analog_date: string;
  narrative: string;
}

export interface PredictionSource {
  market_data: string;
  forecast: string;
  analysis: string | null;
  data_quality: "clean" | "patched" | "degraded";
  data_warnings: string[];
  stale: boolean;
}

export type SupportedCurrency = "USD" | "EUR" | "GBP" | "JPY" | "CHF" | "CAD" | "AUD";

export interface PredictRequest {
  symbol: string;
  horizon: number;
  engine: ForecastEngine;
  asset_type: AssetType;
  display_currency?: SupportedCurrency;
}

export interface PredictResponse {
  symbol: string;
  requested_symbol: string;
  asset_type: AssetType;
  currency: string;
  native_currency?: string;
  display_currency?: string;
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
  explanation: PredictionExplanation | null;
  disclaimer: string;
}
