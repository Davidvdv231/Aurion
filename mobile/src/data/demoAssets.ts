import type {
  AssetType,
  ConfidenceTier,
  ForecastEngine,
  ForecastPoint,
  HistoryPoint,
  PredictResponse,
  SupportedCurrency,
  TickerItem,
} from "@/api/types";

export interface DemoMarketCard {
  symbol: string;
  name: string;
  assetType: AssetType;
  exchange: string;
  region: string;
  source: "demo";
}

const today = new Date();
const DEMO_NATIVE_CURRENCY: SupportedCurrency = "USD";
const DEMO_SYMBOL_ALIASES: Record<string, string> = {
  BTC: "BTC-USD",
  ETH: "ETH-USD",
  SOL: "SOL-USD",
};

function isoDaysAhead(days: number) {
  const date = new Date(today);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function buildForecast(base: number, drift: number, volatility: number): ForecastPoint[] {
  return Array.from({ length: 7 }, (_, index) => {
    const factor = 1 + drift * (index + 1);
    const predicted = base * factor;
    return {
      date: isoDaysAhead(index + 1),
      predicted,
      lower: predicted * (1 - volatility),
      upper: predicted * (1 + volatility),
    };
  });
}

function buildHistory(base: number): HistoryPoint[] {
  return Array.from({ length: 30 }, (_, index) => ({
    date: isoDaysAhead(-(30 - index)),
    close: base * (1 + index * 0.002),
  }));
}

function buildSignal(
  expectedReturnPct: number,
  confidence: number,
): PredictResponse["summary"]["signal"] {
  if (expectedReturnPct > 5 && confidence >= 0.67) return "Strongly Bullish";
  if (expectedReturnPct > 1.5 && confidence >= 0.45) return "Bullish Outlook";
  if (expectedReturnPct < -5 && confidence >= 0.67) return "Strongly Bearish";
  if (expectedReturnPct < -1.5 && confidence >= 0.45) return "Bearish Outlook";
  return "Neutral";
}

export const demoMarketCards: DemoMarketCard[] = [
  {
    symbol: "AAPL",
    name: "Apple",
    assetType: "stock",
    exchange: "NASDAQ",
    region: "US",
    source: "demo",
  },
  {
    symbol: "MSFT",
    name: "Microsoft",
    assetType: "stock",
    exchange: "NASDAQ",
    region: "US",
    source: "demo",
  },
  {
    symbol: "BTC-USD",
    name: "Bitcoin",
    assetType: "crypto",
    exchange: "Crypto",
    region: "GLOBAL",
    source: "demo",
  },
  {
    symbol: "ETH-USD",
    name: "Ethereum",
    assetType: "crypto",
    exchange: "Crypto",
    region: "GLOBAL",
    source: "demo",
  },
];

export const demoTickers: TickerItem[] = [
  { symbol: "AAPL", name: "Apple", exchange: "NASDAQ", region: "US", popularity: 1000, asset_type: "stock" },
  { symbol: "MSFT", name: "Microsoft", exchange: "NASDAQ", region: "US", popularity: 980, asset_type: "stock" },
  { symbol: "NVDA", name: "NVIDIA", exchange: "NASDAQ", region: "US", popularity: 960, asset_type: "stock" },
  { symbol: "BTC-USD", name: "Bitcoin", exchange: "Crypto", region: "GLOBAL", popularity: 1000, asset_type: "crypto" },
  { symbol: "ETH-USD", name: "Ethereum", exchange: "Crypto", region: "GLOBAL", popularity: 960, asset_type: "crypto" },
  { symbol: "SOL-USD", name: "Solana", exchange: "Crypto", region: "GLOBAL", popularity: 890, asset_type: "crypto" },
];

function normalizeDemoSymbol(symbol: string) {
  const normalized = symbol.trim().toUpperCase();
  return DEMO_SYMBOL_ALIASES[normalized] ?? normalized;
}

function demoBasePrice(symbol: string) {
  const prices: Record<string, number> = {
    AAPL: 194.22,
    MSFT: 431.14,
    "BTC-USD": 68240.18,
    "ETH-USD": 3625.74,
  };
  return prices[symbol] ?? 180.0;
}

function demoConfidence(symbol: string) {
  const values: Record<string, number> = {
    AAPL: 0.72,
    MSFT: 0.69,
    "BTC-USD": 0.64,
    "ETH-USD": 0.71,
  };
  return values[symbol] ?? 0.55;
}

function demoTrend(symbol: string): "bullish" | "bearish" | "neutral" {
  const values: Record<string, "bullish" | "bearish" | "neutral"> = {
    AAPL: "bullish",
    MSFT: "bullish",
    "BTC-USD": "neutral",
    "ETH-USD": "bullish",
  };
  return values[symbol] ?? "neutral";
}

export function getDemoForecast(
  symbol: string,
  assetType: AssetType,
  displayCurrency: SupportedCurrency = DEMO_NATIVE_CURRENCY,
  engineRequested: ForecastEngine = "ml",
): PredictResponse {
  const normalizedSymbol = normalizeDemoSymbol(symbol);
  const asset =
    demoMarketCards.find((item) => item.symbol === normalizedSymbol && item.assetType === assetType) ??
    demoMarketCards.find((item) => item.assetType === assetType) ??
    demoMarketCards[0];
  const base = demoBasePrice(asset.symbol);
  const confidence = demoConfidence(asset.symbol);
  const trend = demoTrend(asset.symbol);
  const drift = trend === "bullish" ? 0.012 : trend === "bearish" ? -0.009 : 0.004;
  const volatility = assetType === "crypto" ? 0.08 : 0.04;
  const forecast = buildForecast(base, drift, volatility);
  const expectedPrice = forecast[forecast.length - 1]?.predicted ?? base;
  const expectedReturnPct = ((expectedPrice / base) - 1) * 100;
  const confidenceTier: ConfidenceTier =
    confidence >= 0.67 ? "high" : confidence >= 0.45 ? "medium" : "low";
  const dataWarnings =
    displayCurrency === DEMO_NATIVE_CURRENCY
      ? ["Demo fallback data is shown because the live API is unavailable or not configured."]
      : [
          "Demo fallback data is shown because the live API is unavailable or not configured.",
          `Demo fallback prices are only available in ${DEMO_NATIVE_CURRENCY}; requested ${displayCurrency}.`,
        ];

  return {
    symbol: asset.symbol,
    requested_symbol: normalizedSymbol,
    asset_type: assetType,
    currency: DEMO_NATIVE_CURRENCY,
    native_currency: DEMO_NATIVE_CURRENCY,
    display_currency: DEMO_NATIVE_CURRENCY,
    generated_at: new Date().toISOString(),
    horizon_days: 7,
    engine_requested: engineRequested,
    engine_used: "stat_fallback",
    model_name: "Aurion demo fallback",
    engine_note: "Demo fallback data while the live API is unavailable or not configured.",
    source: {
      market_data: "demo",
      forecast: "demo",
      analysis: null,
      data_quality: "degraded",
      data_warnings: dataWarnings,
      stale: false,
    },
    degraded: true,
    degradation_code: "demo_data_unavailable",
    degradation_message: "Using explicit demo fallback data because the live API is unavailable or not configured.",
    degradation_reason: "Using explicit demo fallback data because the live API is unavailable or not configured.",
    history: buildHistory(base),
    forecast,
    stats: {
      daily_trend_pct: drift * 100,
      last_close: base,
    },
    summary: {
      expected_price: expectedPrice,
      expected_return_pct: expectedReturnPct,
      trend,
      confidence_tier: confidenceTier,
      signal: buildSignal(expectedReturnPct, confidence),
    },
    evaluation: null,
    explanation: null,
    disclaimer: "Demo-only forecast. This is not financial advice.",
  };
}
