import { ApiError, createApiClient } from "@/api/client";
import type { AssetType, ForecastEngine, PredictResponse, SupportedCurrency, TickerItem } from "@/api/types";
import { demoTickers, getDemoForecast } from "@/data/demoAssets";

const api = createApiClient();

export interface TickerListResult {
  items: TickerItem[];
  isDemo: boolean;
  reason?: string;
}

function fallbackReason(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.message) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export async function loadHighlights(assetType: AssetType): Promise<TickerListResult> {
  try {
    const response = await api.topAssets(assetType, 8);
    if (response.items.length > 0) {
      return { items: response.items, isDemo: false };
    }
    return {
      items: demoTickers.filter((item) => item.asset_type === assetType),
      isDemo: true,
      reason: "Top assets endpoint returned no items.",
    };
  } catch (error: unknown) {
    return {
      items: demoTickers.filter((item) => item.asset_type === assetType),
      isDemo: true,
      reason: fallbackReason(error, "Top assets endpoint is unavailable."),
    };
  }
}

export async function searchAssets(query: string, assetType: AssetType): Promise<TickerListResult> {
  try {
    const response = await api.searchTickers(query, assetType, 12);
    return { items: response.tickers, isDemo: false };
  } catch (error: unknown) {
    const needle = query.toUpperCase();
    return {
      items: demoTickers.filter((item) => item.asset_type === assetType && item.symbol.includes(needle)),
      isDemo: true,
      reason: fallbackReason(error, "Search endpoint is unavailable."),
    };
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
  reason?: string;
}

export async function loadForecast(
  symbol: string,
  assetType: AssetType,
  options: ForecastOptions = {},
): Promise<ForecastResult> {
  const { horizon = 7, engine = "ml", displayCurrency } = options;
  try {
    return { data: await api.predict(symbol, assetType, horizon, engine, displayCurrency), isDemo: false };
  } catch (error: unknown) {
    return {
      data: getDemoForecast(symbol, assetType, displayCurrency, engine),
      isDemo: true,
      reason: fallbackReason(error, "Forecast endpoint is unavailable."),
    };
  }
}
