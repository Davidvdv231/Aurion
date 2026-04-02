import { createApiClient } from "@/api/client";
import type { AssetType, PredictResponse, TickerItem } from "@/api/types";
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

export async function loadForecast(symbol: string, assetType: AssetType): Promise<PredictResponse> {
  try {
    return await api.predict(symbol, assetType, 7);
  } catch {
    return getDemoForecast(symbol, assetType);
  }
}

export function findDemoCard(symbol: string) {
  return demoMarketCards.find((item) => item.symbol === symbol.toUpperCase()) ?? demoMarketCards[0];
}

