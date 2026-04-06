import { createApiClient } from "@/api/client";
import type { AssetType, ForecastEngine, PredictResponse, SupportedCurrency, TickerItem } from "@/api/types";
import { demoMarketCards, demoTickers, getDemoForecast } from "@/data/demoAssets";

const api = createApiClient();

export async function loadHighlights(assetType: AssetType) {
  try {
    const response = await api.topAssets(assetType, 8);
    return response.items.length > 0 ? response.items : demoTickers.filter((item) => item.asset_type === assetType);
  } catch {
    return demoTickers.filter((item) => item.asset_type === assetType);
  }
}

export async function searchAssets(query: string, assetType: AssetType): Promise<TickerItem[]> {
  try {
    const response = await api.searchTickers(query, assetType, 12);
    return response.tickers;
  } catch {
    const needle = query.toUpperCase();
    return demoTickers.filter((item) => item.asset_type === assetType && item.symbol.includes(needle));
  }
}

export interface ForecastOptions {
  horizon?: number;
  engine?: ForecastEngine;
  displayCurrency?: SupportedCurrency;
}

export interface ForecastResult {
  data: PredictResponse;
  isDemo: boolean;
}

export async function loadForecast(
  symbol: string,
  assetType: AssetType,
  options: ForecastOptions = {},
): Promise<ForecastResult> {
  const { horizon = 7, engine = "ml", displayCurrency } = options;
  try {
    return { data: await api.predict(symbol, assetType, horizon, engine, displayCurrency), isDemo: false };
  } catch {
    return { data: getDemoForecast(symbol, assetType), isDemo: true };
  }
}

export function findDemoCard(symbol: string) {
  return demoMarketCards.find((item) => item.symbol === symbol.toUpperCase()) ?? demoMarketCards[0];
}

