import type {
  AssetType,
  ForecastEngine,
  PredictRequest,
  PredictResponse,
  SupportedCurrency,
  TickerSearchResponse,
  TopAssetsResponse,
} from "@/api/types";

const LOCAL_DEV_BASE_URL = "http://127.0.0.1:8000";

const REQUEST_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function resolveBaseUrl() {
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, "");
  }
  if (__DEV__) {
    return LOCAL_DEV_BASE_URL;
  }
  throw new ApiError("EXPO_PUBLIC_API_BASE_URL is not configured for this build.", 0);
}

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const baseUrl = resolveBaseUrl();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const callerSignal = init?.signal;
  const cancel = () => controller.abort();
  if (callerSignal?.aborted) cancel();
  callerSignal?.addEventListener("abort", cancel, { once: true });
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const text = await response.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      throw new ApiError(response.ok ? "API returned invalid JSON." : `API request failed with status ${response.status}`, response.ok ? 502 : response.status);
    }
    if (!response.ok) {
      const errorPayload = payload as { error?: { message?: string }; detail?: string } | null;
      const message = errorPayload?.error?.message || errorPayload?.detail;
      throw new ApiError(typeof message === "string" ? message : `API request failed with status ${response.status}`, response.status);
    }
    return payload as T;
  } catch (err: unknown) {
    if (controller.signal.aborted && !callerSignal?.aborted) {
      throw new ApiError("Request timed out", 0);
    }
    throw err;
  } finally {
    clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", cancel);
  }
}

const isText = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isPositive = (value: unknown): value is number => isFiniteNumber(value) && value > 0;
const isOptionalText = (value: unknown) => value == null || isText(value);

function validateTickerList(items: unknown): void {
  if (!Array.isArray(items) || !items.every(item => item
      && isText(item.symbol) && item.symbol.length > 0 && isText(item.name)
      && isText(item.exchange) && isText(item.region) && isFiniteNumber(item.popularity)
      && ["stock", "crypto"].includes(item.asset_type))) {
    throw new ApiError("API returned invalid ticker data.", 502);
  }
}

function validatePrediction(data: PredictResponse, horizon: number): PredictResponse {
  if (!data || typeof data.symbol !== "string" || !isPositive(data.stats?.last_close)
      || !isPositive(data.summary?.expected_price) || !isFiniteNumber(data.summary?.expected_return_pct)
      || !["bullish", "bearish", "neutral"].includes(data.summary?.trend)
      || !["low", "medium", "high"].includes(data.summary?.confidence_tier)
      || !isText(data.summary?.signal)
      || ![data.currency, data.engine_note, data.disclaimer].every(isText)
      || ![data.degradation_message, data.degradation_reason].every(isOptionalText)
      || !data.source || ![data.source.market_data, data.source.forecast].every(isText)
      || !Array.isArray(data.source.data_warnings) || !data.source.data_warnings.every(isText)
      || !Array.isArray(data.history) || data.history.length === 0
      || !data.history.every(point => point && isText(point.date) && isPositive(point.close))
      || !Array.isArray(data.forecast) || data.forecast.length !== horizon
      || !data.forecast.every(point => point && isText(point.date)
        && [point.predicted, point.lower, point.upper].every(isPositive)
        && point.lower <= point.predicted && point.predicted <= point.upper)) {
    throw new ApiError("API returned invalid forecast data.", 502);
  }
  const evaluation = data.evaluation;
  if (evaluation != null && (typeof evaluation !== "object"
      || ![evaluation.mae, evaluation.rmse, evaluation.mape, evaluation.directional_accuracy,
        evaluation.validation_windows].every(value => value == null || isFiniteNumber(value)))) {
    throw new ApiError("API returned invalid forecast evaluation.", 502);
  }
  const explanation = data.explanation;
  if (explanation != null && (!isText(explanation.narrative)
      || !isOptionalText(explanation.nearest_analog_date)
      || !Array.isArray(explanation.top_features)
      || !explanation.top_features.every(feature => feature && isText(feature.feature)
        && ["higher", "lower", "similar"].includes(feature.relation)))) {
    throw new ApiError("API returned invalid forecast data.", 502);
  }
  return data;
}

export function createApiClient() {
  return {
    health: () => requestJson<{ status: string; timestamp: string }>("/api/health"),
    searchTickers: (query: string, assetType: AssetType, limit = 12) =>
      requestJson<TickerSearchResponse>(
        `/api/tickers?query=${encodeURIComponent(query)}&asset_type=${assetType}&limit=${limit}`,
      ).then(data => { validateTickerList(data?.tickers); return data; }),
    topAssets: (assetType: AssetType, limit = 8) =>
      requestJson<TopAssetsResponse>(`/api/top-assets?asset_type=${assetType}&limit=${limit}`)
        .then(data => { validateTickerList(data?.items); return data; }),
    predict: (
      symbol: string,
      assetType: AssetType,
      horizon = 7,
      engine: ForecastEngine = "ml",
      displayCurrency?: SupportedCurrency,
      signal?: AbortSignal,
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
        signal,
      }, 90_000).then(data => validatePrediction(data, horizon));
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
