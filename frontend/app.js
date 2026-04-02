const form = document.getElementById("predict-form");
const assetTypeInput = document.getElementById("asset-type");
const engineInput = document.getElementById("engine");
const symbolInput = document.getElementById("symbol");
const horizonInput = document.getElementById("horizon");
const symbolHelpNode = document.getElementById("symbol-help");
const topTitleNode = document.getElementById("top-title");
const suggestionsNode = document.getElementById("ticker-suggestions");
const topAssetsNode = document.getElementById("top-assets");
const statusNode = document.getElementById("status");
const statsCard = document.getElementById("stats-card");
const lastCloseNode = document.getElementById("last-close");
const trendNode = document.getElementById("trend");
const modelNameNode = document.getElementById("model-name");
const expectedReturnNode = document.getElementById("expected-return");
const trendLabelNode = document.getElementById("trend-label");
const confidenceScoreNode = document.getElementById("confidence-score");
const signalLabelNode = document.getElementById("signal-label");
const disclaimerNode = document.getElementById("disclaimer");
const sourceBadgeNode = document.getElementById("source-badge");
const degradedBadgeNode = document.getElementById("degraded-badge");
const evaluationRowNode = document.getElementById("evaluation-row");
const metricMaeNode = document.getElementById("metric-mae");
const metricDirectionNode = document.getElementById("metric-direction");
const chartFallbackNode = document.getElementById("chart-fallback");
const submitButton = document.getElementById("submit-btn");

const state = {
  chart: undefined,
  suggestionTimer: undefined,
  suggestionItems: [],
  activeSuggestionIndex: -1,
  suggestionRequestId: 0,
  topAssetsRequestId: 0,
  predictionRequestId: 0,
  activeSuggestionController: undefined,
  activeTopAssetsController: undefined,
  activePredictionController: undefined,
  uiState: "idle",
};

function currentAssetType() {
  return assetTypeInput.value === "crypto" ? "crypto" : "stock";
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.style.color = isError ? "#dc2626" : "#1d4ed8";
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Bezig..." : "Toon voorspelling";
}

function formatApiError(payload, fallbackMessage) {
  if (payload && typeof payload === "object") {
    if (payload.error && typeof payload.error.message === "string") {
      return payload.error.message;
    }

    const detail = payload.detail;
    if (Array.isArray(detail)) {
      const first = detail[0];
      if (first && typeof first === "object" && typeof first.msg === "string") {
        return first.msg;
      }
    }

    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }

  return fallbackMessage;
}

function formatCurrency(value, currency) {
  try {
    return new Intl.NumberFormat("nl-BE", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    const amount = Number.isFinite(value) ? value.toFixed(2) : "0.00";
    return `${amount} ${currency || "USD"}`;
  }
}

function hideSuggestions() {
  state.suggestionItems = [];
  state.activeSuggestionIndex = -1;
  symbolInput.setAttribute("aria-expanded", "false");
  symbolInput.removeAttribute("aria-activedescendant");
  suggestionsNode.hidden = true;
  suggestionsNode.innerHTML = "";
}

function selectSuggestion(item) {
  symbolInput.value = item.symbol;
  hideSuggestions();
  form.requestSubmit();
}

function updateActiveSuggestion(nextIndex) {
  const count = state.suggestionItems.length;
  if (!count) {
    state.activeSuggestionIndex = -1;
    symbolInput.removeAttribute("aria-activedescendant");
    return;
  }

  const normalizedIndex = ((nextIndex % count) + count) % count;
  state.activeSuggestionIndex = normalizedIndex;

  const buttons = suggestionsNode.querySelectorAll(".suggestion-item");
  for (const [index, button] of buttons.entries()) {
    const isActive = index === normalizedIndex;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    if (isActive) {
      symbolInput.setAttribute("aria-activedescendant", button.id);
      button.scrollIntoView({ block: "nearest" });
    }
  }
}

function clearResults() {
  statsCard.hidden = true;
  sourceBadgeNode.hidden = true;
  degradedBadgeNode.hidden = true;
  evaluationRowNode.hidden = true;
  disclaimerNode.textContent = "";
  chartFallbackNode.hidden = true;
  chartFallbackNode.textContent = "";
  expectedReturnNode.textContent = "-";
  trendLabelNode.textContent = "-";
  confidenceScoreNode.textContent = "-";
  signalLabelNode.textContent = "-";
  metricMaeNode.textContent = "MAE: -";
  metricDirectionNode.textContent = "Directional accuracy: -";

  if (state.chart) {
    state.chart.destroy();
    state.chart = undefined;
  }
}

function applyAssetTypeUi() {
  const assetType = currentAssetType();

  if (assetType === "crypto") {
    symbolHelpNode.textContent = "Crypto: BTC, ETH, SOL, XRP, DOGE...";
    topTitleNode.textContent = "Top 10 Crypto Nu";

    const current = symbolInput.value.trim().toUpperCase();
    if (!current || current === "AAPL") {
      symbolInput.value = "BTC";
    }
    return;
  }

  symbolHelpNode.textContent = "Aandelen: AAPL, INGA, KBC | Crypto: BTC, ETH, SOL";
  topTitleNode.textContent = "Top 10 Aandelen Nu";

  const current = symbolInput.value.trim().toUpperCase();
  if (!current || current === "BTC" || current.endsWith("-USD")) {
    symbolInput.value = "AAPL";
  }
}

function renderSuggestions(tickers) {
  suggestionsNode.innerHTML = "";
  state.suggestionItems = Array.isArray(tickers) ? tickers : [];
  state.activeSuggestionIndex = -1;

  if (state.suggestionItems.length === 0) {
    hideSuggestions();
    return;
  }

  for (const [index, item] of state.suggestionItems.entries()) {
    const listItem = document.createElement("li");
    const button = document.createElement("button");
    const symbolSpan = document.createElement("span");
    const nameSpan = document.createElement("span");

    button.type = "button";
    button.className = "suggestion-item";
    button.id = `suggestion-${index}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");

    symbolSpan.className = "suggestion-symbol";
    symbolSpan.textContent = item.symbol;

    nameSpan.className = "suggestion-name";
    nameSpan.textContent = `${item.name} (${item.exchange})`;

    button.appendChild(symbolSpan);
    button.appendChild(nameSpan);

    button.addEventListener("click", () => selectSuggestion(item));

    listItem.appendChild(button);
    suggestionsNode.appendChild(listItem);
  }

  symbolInput.setAttribute("aria-expanded", "true");
  suggestionsNode.hidden = false;
}

async function loadSuggestions() {
  const query = symbolInput.value.trim();
  const assetType = currentAssetType();

  if (!query) {
    hideSuggestions();
    return;
  }

  if (state.activeSuggestionController) {
    state.activeSuggestionController.abort();
  }

  const currentRequestId = ++state.suggestionRequestId;
  const controller = new AbortController();
  state.activeSuggestionController = controller;

  try {
    const response = await fetch(
      `/api/tickers?query=${encodeURIComponent(query)}&limit=12&asset_type=${encodeURIComponent(assetType)}`,
      { signal: controller.signal },
    );
    const data = await response.json();

    if (currentRequestId !== state.suggestionRequestId) {
      return;
    }

    if (!response.ok) {
      hideSuggestions();
      return;
    }

    renderSuggestions(data.tickers || []);
  } catch (error) {
    if (error?.name !== "AbortError" && currentRequestId === state.suggestionRequestId) {
      hideSuggestions();
    }
  }
}

function queueSuggestionsLoad() {
  clearTimeout(state.suggestionTimer);
  state.suggestionTimer = setTimeout(loadSuggestions, 140);
}

function renderTopAssets(items) {
  topAssetsNode.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    topAssetsNode.textContent = "Geen top tickers beschikbaar.";
    return;
  }

  for (const item of items) {
    const button = document.createElement("button");
    const symbol = document.createElement("span");
    const name = document.createElement("span");

    button.type = "button";
    button.className = "chip-btn";

    symbol.className = "chip-symbol";
    symbol.textContent = item.symbol;

    name.className = "chip-name";
    name.textContent = item.name;

    button.title = `${item.symbol} - ${item.name}`;
    button.appendChild(symbol);
    button.appendChild(name);

    button.addEventListener("click", () => {
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });

    topAssetsNode.appendChild(button);
  }
}

async function loadTopAssets() {
  topAssetsNode.textContent = "Top 10 laden...";
  const assetType = currentAssetType();
  const currentRequestId = ++state.topAssetsRequestId;

  if (state.activeTopAssetsController) {
    state.activeTopAssetsController.abort();
  }

  const controller = new AbortController();
  state.activeTopAssetsController = controller;

  if (navigator.onLine === false) {
    topAssetsNode.textContent = "Offline: top assets vereisen een netwerkverbinding.";
    return;
  }

  try {
    const response = await fetch(
      `/api/top-assets?limit=10&asset_type=${encodeURIComponent(assetType)}`,
      { signal: controller.signal },
    );

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (currentRequestId !== state.topAssetsRequestId) {
      return;
    }

    if (!response.ok) {
      topAssetsNode.textContent = formatApiError(data, "Top 10 kon niet worden geladen.");
      return;
    }

    renderTopAssets(data?.items || []);
  } catch (error) {
    if (error?.name === "AbortError" || currentRequestId !== state.topAssetsRequestId) {
      return;
    }
    topAssetsNode.textContent = "Top 10 kon niet worden geladen.";
  }
}

function buildDatasets(history, forecast) {
  const historyDates = history.map((row) => row.date);
  const forecastDates = forecast.map((row) => row.date);
  const labels = [...historyDates, ...forecastDates];

  const historyPrices = history.map((row) => row.close);
  const historyData = [...historyPrices, ...Array(forecast.length).fill(null)];
  const lastHistoricalPrice = historyPrices[historyPrices.length - 1];

  const forecastLine = [
    ...Array(history.length - 1).fill(null),
    lastHistoricalPrice,
    ...forecast.map((row) => row.predicted),
  ];

  const lowerBand = [...Array(history.length).fill(null), ...forecast.map((row) => row.lower)];
  const upperBand = [...Array(history.length).fill(null), ...forecast.map((row) => row.upper)];

  return { labels, historyData, forecastLine, lowerBand, upperBand };
}

function renderChart(data) {
  if (typeof window.Chart !== "function") {
    throw new Error("Grafiekbibliotheek ontbreekt. Herlaad de pagina of controleer de offline cache.");
  }

  const canvas = document.getElementById("stock-chart");
  const ctx = canvas.getContext("2d");
  const { labels, historyData, forecastLine, lowerBand, upperBand } = buildDatasets(
    data.history,
    data.forecast,
  );

  const config = {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Historiek",
          data: historyData,
          borderColor: "#0b172a",
          borderWidth: 2,
          tension: 0.25,
          pointRadius: 0,
        },
        {
          label: "Voorspelling",
          data: forecastLine,
          borderColor: "#1d4ed8",
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.3,
          pointRadius: 0,
        },
        {
          label: "Ondergrens (80%)",
          data: lowerBand,
          borderColor: "#94a3b8",
          borderWidth: 1,
          pointRadius: 0,
        },
        {
          label: "Bovengrens (80%)",
          data: upperBand,
          borderColor: "#94a3b8",
          borderWidth: 1,
          pointRadius: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 8,
          },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
        },
      },
    },
  };

  if (state.chart) {
    state.chart.destroy();
  }
  state.chart = new window.Chart(ctx, config);
}

function updateStats(data) {
  statsCard.hidden = false;
  lastCloseNode.textContent = formatCurrency(data.stats.last_close, data.currency);

  const sign = data.stats.daily_trend_pct >= 0 ? "+" : "";
  trendNode.textContent = `${sign}${data.stats.daily_trend_pct.toFixed(3)}% / dag`;
  modelNameNode.textContent = data.model_name;
  updateSummary(data.summary);
  updateEvaluation(data.evaluation);
  sourceBadgeNode.hidden = false;
  sourceBadgeNode.textContent = `Bronnen: ${data.source.market_data} / ${data.source.forecast}`;

  if (data.degraded) {
    degradedBadgeNode.hidden = false;
    degradedBadgeNode.textContent = data.degradation_reason
      ? `Fallback actief: ${data.degradation_reason}`
      : "Fallback actief";
  } else {
    degradedBadgeNode.hidden = true;
  }

  disclaimerNode.textContent = `${data.disclaimer} ${data.engine_note || ""}`.trim();
}

function updateSummary(summary) {
  if (!summary || typeof summary !== "object") {
    expectedReturnNode.textContent = "-";
    trendLabelNode.textContent = "-";
    confidenceScoreNode.textContent = "-";
    signalLabelNode.textContent = "-";
    return;
  }

  const expectedReturn = Number(summary.expected_return_pct);
  const confidence = Number(summary.confidence_score);
  const probabilityUp = Number(summary.probability_up);

  if (Number.isFinite(expectedReturn)) {
    const sign = expectedReturn >= 0 ? "+" : "";
    expectedReturnNode.textContent = `${sign}${expectedReturn.toFixed(2)}%`;
  } else {
    expectedReturnNode.textContent = "-";
  }

  trendLabelNode.textContent = typeof summary.trend === "string" ? summary.trend : "-";
  signalLabelNode.textContent = typeof summary.signal === "string" ? summary.signal : "-";

  if (Number.isFinite(confidence)) {
    const confidencePct = (confidence * 100).toFixed(0);
    const probabilityText = Number.isFinite(probabilityUp) ? ` | up ${Math.round(probabilityUp * 100)}%` : "";
    confidenceScoreNode.textContent = `${confidencePct}%${probabilityText}`;
  } else {
    confidenceScoreNode.textContent = "-";
  }
}

function updateEvaluation(evaluation) {
  if (!evaluation || typeof evaluation !== "object") {
    evaluationRowNode.hidden = true;
    return;
  }

  const mae = Number(evaluation.mae);
  const directionalAccuracy = Number(evaluation.directional_accuracy);
  metricMaeNode.textContent = Number.isFinite(mae) ? `MAE: ${mae.toFixed(2)}` : "MAE: -";
  metricDirectionNode.textContent = Number.isFinite(directionalAccuracy)
    ? `Directional accuracy: ${(directionalAccuracy * 100).toFixed(0)}%`
    : "Directional accuracy: -";
  evaluationRowNode.hidden = false;
}

async function fetchPrediction(payload, controller) {
  const response = await fetch("/api/predict", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    signal: controller.signal,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const error = new Error(formatApiError(data, "Fout bij ophalen van data."));
    error.isApiError = true;
    error.statusCode = response.status;
    throw error;
  }

  return data;
}

async function loadPrediction(event) {
  event.preventDefault();

  const symbol = symbolInput.value.trim().toUpperCase();
  const horizon = Number.parseInt(horizonInput.value, 10);
  const engine = ["ml", "ai", "stat"].includes(engineInput.value) ? engineInput.value : "ml";
  const assetType = currentAssetType();

  if (!symbol) {
    clearResults();
    setStatus("Vul een ticker symbool in.", true);
    return;
  }

  if (!Number.isInteger(horizon) || horizon < 7 || horizon > 45) {
    clearResults();
    setStatus("Horizon moet tussen 7 en 45 dagen liggen.", true);
    return;
  }

  if (navigator.onLine === false) {
    clearResults();
    state.uiState = "error";
    setStatus("Je bent offline. Voorspellingen vereisen een netwerkverbinding.", true);
    return;
  }

  symbolInput.value = symbol;
  hideSuggestions();
  clearResults();
  state.uiState = "loading";
  setLoading(true);
  setStatus("Data laden en voorspelling berekenen...");

  if (state.activePredictionController) {
    state.activePredictionController.abort();
  }

  const controller = new AbortController();
  state.activePredictionController = controller;
  const currentRequestId = ++state.predictionRequestId;

  try {
    const data = await fetchPrediction(
      {
        symbol,
        horizon,
        engine,
        asset_type: assetType,
      },
      controller,
    );

    if (currentRequestId !== state.predictionRequestId) {
      return;
    }

    try {
      renderChart(data);
      updateStats(data);
    } catch (renderError) {
      clearResults();
      chartFallbackNode.hidden = false;
      chartFallbackNode.textContent = renderError.message || "Grafiek renderen mislukt.";
      state.uiState = "error";
      setStatus(chartFallbackNode.textContent, true);
      return;
    }

    state.uiState = "success";
    const requested = data.requested_symbol || symbol;
    const symbolLabel = requested !== data.symbol ? `${requested} -> ${data.symbol}` : data.symbol;
    const assetLabel = data.asset_type === "crypto" ? "crypto" : "aandeel";

    if (data.degraded) {
      setStatus(`Voorspelling geladen voor ${symbolLabel} (${assetLabel}) met fallback.`);
      return;
    }

    setStatus(`Voorspelling geladen voor ${symbolLabel} (${assetLabel}, ${data.engine_used}).`);
  } catch (error) {
    if (error?.name === "AbortError" || currentRequestId !== state.predictionRequestId) {
      return;
    }

    clearResults();
    state.uiState = "error";
    setStatus(error?.message || "Netwerkfout: kan de API niet bereiken.", true);
  } finally {
    if (currentRequestId === state.predictionRequestId) {
      setLoading(false);
    }
  }
}

form.addEventListener("submit", loadPrediction);
assetTypeInput.addEventListener("change", () => {
  applyAssetTypeUi();
  hideSuggestions();
  clearResults();
  loadTopAssets();
  queueSuggestionsLoad();
});
symbolInput.addEventListener("input", queueSuggestionsLoad);
symbolInput.addEventListener("focus", queueSuggestionsLoad);
symbolInput.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    if (suggestionsNode.hidden) {
      queueSuggestionsLoad();
      return;
    }
    event.preventDefault();
    updateActiveSuggestion(state.activeSuggestionIndex + 1);
    return;
  }

  if (event.key === "ArrowUp") {
    if (suggestionsNode.hidden) {
      return;
    }
    event.preventDefault();
    updateActiveSuggestion(state.activeSuggestionIndex - 1);
    return;
  }

  if (event.key === "Enter" && !suggestionsNode.hidden && state.activeSuggestionIndex >= 0) {
    event.preventDefault();
    selectSuggestion(state.suggestionItems[state.activeSuggestionIndex]);
    return;
  }

  if (event.key === "Escape") {
    hideSuggestions();
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".autocomplete-wrap")) {
    hideSuggestions();
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Non-blocking if registration fails.
    });
  });
}

window.addEventListener("online", () => {
  if (state.uiState === "error" && statusNode.textContent.includes("offline")) {
    setStatus("Verbinding hersteld. Je kunt opnieuw een voorspelling opvragen.");
  }
  loadTopAssets();
});

window.addEventListener("offline", () => {
  topAssetsNode.textContent = "Offline: top assets vereisen een netwerkverbinding.";
  if (state.uiState !== "loading") {
    setStatus("Je bent offline. De app-shell blijft beschikbaar, maar live data niet.", true);
  }
});

window.__stockPredictor = {
  formatCurrency,
};

applyAssetTypeUi();
loadTopAssets();
setStatus("Kies een ticker en vraag een voorspelling op.");
