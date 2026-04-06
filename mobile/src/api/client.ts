import type { AssetType, ForecastEngine, PredictRequest, PredictResponse, SupportedCurrency, TickerSearchResponse, TopAssetsResponse } from "@/api/types";

const DEFAULT_BASE_URL = __DEV__ ? "http://127.0.0.1:8000" : "https://aurion.example.com";

const REQUEST_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function resolveBaseUrl() {
  return process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || DEFAULT_BASE_URL;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${resolveBaseUrl()}${path}`, {
      headers: {
        Accept: "application/json",
        ...(init?.headers || {}),
      },
      ...init,
      signal: controller.signal,
    });
  } catch (err: unknown) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("Request timed out", 0);
    }
    throw err;
  }
  clearTimeout(timeout);

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    const errorPayload = payload as { error?: { message?: string }; detail?: string } | null;
    const message =
      errorPayload?.error?.message || errorPayload?.detail || `API request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
}

export function createApiClient() {
  return {
    health: () => requestJson<{ status: string; timestamp: string }>("/api/health"),
    searchTickers: (query: string, assetType: AssetType, limit = 12) =>
      requestJson<TickerSearchResponse>(
        `/api/tickers?query=${encodeURIComponent(query)}&asset_type=${assetType}&limit=${limit}`,
      ),
    topAssets: (assetType: AssetType, limit = 8) =>
      requestJson<TopAssetsResponse>(`/api/top-assets?asset_type=${assetType}&limit=${limit}`),
    predict: (
      symbol: string,
      assetType: AssetType,
      horizon = 7,
      engine: ForecastEngine = "ml",
      displayCurrency?: SupportedCurrency,
    ) => {
      const body: PredictRequest = {
        symbol,
        asset_type: assetType,
        horizon,
        engine,
      };
      if (displayCurrency) {
        body.display_currency = displayCurrency;
      }
      return requestJson<PredictResponse>("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
