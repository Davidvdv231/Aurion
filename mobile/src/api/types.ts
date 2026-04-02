export type AssetType = "stock" | "crypto";
export type ForecastEngine = "stat" | "ml";

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

export interface PredictResponse {
  symbol: string;
  requested_symbol: string;
  asset_type: AssetType;
  currency: string;
  generated_at: string;
  horizon_days: number;
  engine_requested: "stat" | "ai";
  engine_used: "stat" | "ai" | "stat_fallback";
  model_name: string;
  engine_note: string;
  source: {
    market_data: string;
    forecast: string;
  };
  degraded: boolean;
  degradation_reason: string | null;
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  stats: {
    daily_trend_pct: number;
    last_close: number;
  };
  disclaimer: string;
}

