import type { AssetType, ForecastPoint, HistoryPoint, PredictResponse, TickerItem } from "@/api/types";

export interface DemoMarketCard {
  symbol: string;
  name: string;
  assetType: AssetType;
  price: number;
  changePct: number;
  confidence: number;
  trend: "bullish" | "bearish" | "neutral";
}

const today = new Date();

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

export const demoMarketCards: DemoMarketCard[] = [
  {
    symbol: "AAPL",
    name: "Apple",
    assetType: "stock",
    price: 194.22,
    changePct: 1.84,
    confidence: 0.72,
    trend: "bullish",
  },
  {
    symbol: "MSFT",
    name: "Microsoft",
    assetType: "stock",
    price: 431.14,
    changePct: 0.92,
    confidence: 0.69,
    trend: "bullish",
  },
  {
    symbol: "BTC",
    name: "Bitcoin",
    assetType: "crypto",
    price: 68240.18,
    changePct: -0.48,
    confidence: 0.64,
    trend: "neutral",
  },
  {
    symbol: "ETH",
    name: "Ethereum",
    assetType: "crypto",
    price: 3625.74,
    changePct: 2.16,
    confidence: 0.71,
    trend: "bullish",
  },
];

export const demoTickers: TickerItem[] = [
  { symbol: "AAPL", name: "Apple", exchange: "NASDAQ", region: "US", popularity: 1000, asset_type: "stock" },
  { symbol: "MSFT", name: "Microsoft", exchange: "NASDAQ", region: "US", popularity: 980, asset_type: "stock" },
  { symbol: "NVDA", name: "NVIDIA", exchange: "NASDAQ", region: "US", popularity: 960, asset_type: "stock" },
  { symbol: "BTC", name: "Bitcoin", exchange: "Coinbase", region: "Global", popularity: 1000, asset_type: "crypto" },
  { symbol: "ETH", name: "Ethereum", exchange: "Coinbase", region: "Global", popularity: 960, asset_type: "crypto" },
  { symbol: "SOL", name: "Solana", exchange: "Coinbase", region: "Global", popularity: 890, asset_type: "crypto" },
];

export function getDemoForecast(symbol: string, assetType: AssetType): PredictResponse {
  const asset = demoMarketCards.find((item) => item.symbol === symbol.toUpperCase()) ?? demoMarketCards[0];
  const base = asset.price;
  const drift = asset.trend === "bullish" ? 0.012 : asset.trend === "bearish" ? -0.009 : 0.004;
  const volatility = assetType === "crypto" ? 0.08 : 0.04;

  return {
    symbol: asset.symbol,
    requested_symbol: symbol.toUpperCase(),
    asset_type: assetType,
    currency: "USD",
    generated_at: new Date().toISOString(),
    horizon_days: 7,
    engine_requested: "stat",
    engine_used: "stat",
    model_name: "Demo analog forecast",
    engine_note: "Fallback-demo data while backend is unavailable.",
    source: { market_data: "demo", forecast: "demo" },
    degraded: true,
    degradation_reason: "Fallback demo data",
    history: buildHistory(base),
    forecast: buildForecast(base, drift, volatility),
    stats: {
      daily_trend_pct: drift * 100,
      last_close: base,
    },
    disclaimer: "Demo-only forecast. This is not financial advice.",
  };
}

