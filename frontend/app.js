/* ============================================
   AURION - AI Market Intelligence
   Frontend Application
   ============================================ */

// --- DOM References ---
const form = document.getElementById("predict-form");
const assetTypeInput = document.getElementById("asset-type");
const assetTypeControl = document.getElementById("asset-type-control");
const engineInput = document.getElementById("engine");
const engineControl = document.getElementById("engine-control");
const symbolInput = document.getElementById("symbol");
const horizonInput = document.getElementById("horizon");
const horizonValue = document.getElementById("horizon-value");
const topTitleNode = document.getElementById("top-title");
const suggestionsNode = document.getElementById("ticker-suggestions");
const topAssetsNode = document.getElementById("top-assets");
const statusNode = document.getElementById("status");
const submitButton = document.getElementById("submit-btn");
const btnText = submitButton.querySelector(".btn-text");
const btnLoader = submitButton.querySelector(".btn-loader");

// Signal card
const signalCard = document.getElementById("signal-card");
const signalBadge = document.getElementById("signal-badge");
const signalSymbol = document.getElementById("signal-symbol");
const signalEngine = document.getElementById("signal-engine");
const currencyTag = document.getElementById("currency-tag");
const metricPrice = document.getElementById("metric-price");
const metricExpected = document.getElementById("metric-expected");
const metricReturn = document.getElementById("metric-return");
const metricTrend = document.getElementById("metric-trend");
const confidenceFill = document.getElementById("confidence-fill");
const confidenceValue = document.getElementById("confidence-value");
const evalRow = document.getElementById("eval-row");
const evalMae = document.getElementById("eval-mae");
const evalDir = document.getElementById("eval-dir");
const evalMape = document.getElementById("eval-mape");
const sourceBadgeNode = document.getElementById("source-badge");
const degradedBadgeNode = document.getElementById("degraded-badge");

// Explanation card
const explanationCard = document.getElementById("explanation-card");
const explanationSource = document.getElementById("explanation-source");
const explanationNote = document.getElementById("explanation-note");
const explanationNarrative = document.getElementById("explanation-narrative");
const explanationFeatures = document.getElementById("explanation-features");
const explanationAnalog = document.getElementById("explanation-analog");
const explanationToggle = document.getElementById("explanation-toggle");

// Disclaimer banner
const disclaimerBanner = document.getElementById("disclaimer-banner");

// Chart
const chartHeader = document.getElementById("chart-header");
const chartTitle = document.getElementById("chart-title");
const chartSubtitle = document.getElementById("chart-subtitle");
const chartEmpty = document.getElementById("chart-empty");
const chartCanvas = document.getElementById("stock-chart");
const chartFallbackNode = document.getElementById("chart-fallback");
const disclaimerNode = document.getElementById("disclaimer");

// Theme
const themeToggle = document.getElementById("theme-toggle");
const themeIconDark = document.getElementById("theme-icon-dark");
const themeIconLight = document.getElementById("theme-icon-light");

// Watchlist
const watchlistAddBtn = document.getElementById("watchlist-add");
const watchlistItems = document.getElementById("watchlist-items");

// --- State ---
const state = {
  chart: undefined,
  suggestionTimer: undefined,
  suggestionRequestId: 0,
  topAssetsRequestId: 0,
  predictionRequestId: 0,
  activeSuggestionController: undefined,
  activeTopAssetsController: undefined,
  activePredictionController: undefined,
  lastPrediction: null,
  activeSuggestionIndex: -1,
};

// =============================================
// THEME
// =============================================
function initTheme() {
  const saved = localStorage.getItem("aurion-theme");
  const theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  updateThemeIcons(theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("aurion-theme", next);
  updateThemeIcons(next);
  if (state.chart) updateChartTheme(state.chart);
}

function updateThemeIcons(theme) {
  themeIconDark.style.display = theme === "dark" ? "block" : "none";
  themeIconLight.style.display = theme === "light" ? "block" : "none";
}

function getChartColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    history: style.getPropertyValue("--chart-history").trim(),
    forecast: style.getPropertyValue("--chart-forecast").trim(),
    band: style.getPropertyValue("--chart-band").trim(),
    grid: style.getPropertyValue("--chart-grid").trim(),
    text: style.getPropertyValue("--text-muted").trim(),
  };
}

function updateChartTheme(chart) {
  const colors = getChartColors();
  chart.options.scales.x.ticks.color = colors.text;
  chart.options.scales.y.ticks.color = colors.text;
  chart.options.scales.x.grid.color = colors.grid;
  chart.options.scales.y.grid.color = colors.grid;
  chart.data.datasets[0].borderColor = colors.history;
  chart.data.datasets[1].borderColor = colors.forecast;
  chart.data.datasets[2].borderColor = "transparent";
  chart.data.datasets[2].backgroundColor = colors.band;
  chart.data.datasets[3].borderColor = "transparent";
  chart.update("none");
}

// =============================================
// SEGMENTED CONTROLS
// =============================================
function initSegmentedControls() {
  setupSegmented(assetTypeControl, assetTypeInput, () => {
    applyAssetTypeUi();
    hideSuggestions();
    clearResults();
    loadTopAssets();
  });
  setupSegmented(engineControl, engineInput);
}

function setupSegmented(control, hiddenInput, onChange) {
  const buttons = control.querySelectorAll(".seg-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      hiddenInput.value = btn.dataset.value;
      if (onChange) onChange(btn.dataset.value);
    });
  });
}

// =============================================
// HORIZON SLIDER
// =============================================
function initHorizon() {
  horizonInput.addEventListener("input", () => {
    horizonValue.textContent = `${horizonInput.value}d`;
  });
}

// =============================================
// HELPERS
// =============================================
function currentAssetType() {
  return assetTypeInput.value === "crypto" ? "crypto" : "stock";
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.className = isError ? "global-status error" : "global-status";
  if (message) {
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(() => { statusNode.textContent = ""; }, 5000);
  }
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  btnText.hidden = isLoading;
  btnLoader.hidden = !isLoading;
}

function formatApiError(payload, fallback) {
  if (payload && typeof payload === "object") {
    if (payload.error && typeof payload.error.message === "string") return payload.error.message;
    const detail = payload.detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function formatCurrency(value, currency) {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${Number.isFinite(value) ? value.toFixed(2) : "0.00"} ${currency || "USD"}`;
  }
}

function formatPercent(value) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatSourceLabel(value) {
  const labels = {
    stat: "Statistical baseline",
    stat_fallback: "Statistical fallback",
    ml_analog: "ML analog analysis",
    ml_pattern_difference: "Pattern-difference analysis",
    ai: "AI forecast",
    unknown: "Unknown",
  };
  return labels[value] || String(value || "Unknown").replace(/_/g, " ");
}

// =============================================
// UI STATE
// =============================================
function hideSuggestions() {
  suggestionsNode.hidden = true;
  suggestionsNode.innerHTML = "";
  state.activeSuggestionIndex = -1;
}

function clearResults() {
  signalCard.hidden = true;
  explanationCard.hidden = true;
  disclaimerBanner.hidden = true;
  chartHeader.hidden = true;
  chartEmpty.hidden = false;
  chartCanvas.hidden = true;
  chartFallbackNode.hidden = true;
  disclaimerNode.hidden = true;
  sourceBadgeNode.hidden = true;
  degradedBadgeNode.hidden = true;
  evalRow.hidden = true;
  watchlistAddBtn.hidden = true;
  if (state.chart) {
    state.chart.destroy();
    state.chart = undefined;
  }
}

function applyAssetTypeUi() {
  const assetType = currentAssetType();
  topTitleNode.textContent = assetType === "crypto" ? "Trending Crypto" : "Trending Stocks";
  const current = symbolInput.value.trim().toUpperCase();
  if (assetType === "crypto") {
    if (!current || current === "AAPL") symbolInput.value = "BTC";
  } else {
    if (!current || current === "BTC" || current.endsWith("-USD")) symbolInput.value = "AAPL";
  }
}

// =============================================
// AUTOCOMPLETE with keyboard navigation
// =============================================
function renderSuggestions(tickers) {
  suggestionsNode.innerHTML = "";
  state.activeSuggestionIndex = -1;
  if (!Array.isArray(tickers) || tickers.length === 0) {
    hideSuggestions();
    return;
  }

  for (let i = 0; i < tickers.length; i++) {
    const item = tickers[i];
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "suggestion-item";
    btn.dataset.index = i;
    btn.innerHTML = `<span class="suggestion-symbol">${item.symbol}</span><span class="suggestion-name">${item.name} (${item.exchange})</span>`;
    btn.addEventListener("click", () => {
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });
    li.appendChild(btn);
    suggestionsNode.appendChild(li);
  }
  suggestionsNode.hidden = false;
}

function updateSuggestionHighlight() {
  const items = suggestionsNode.querySelectorAll(".suggestion-item");
  items.forEach((item, i) => {
    item.classList.toggle("active", i === state.activeSuggestionIndex);
  });
  // Scroll active item into view
  if (state.activeSuggestionIndex >= 0 && items[state.activeSuggestionIndex]) {
    items[state.activeSuggestionIndex].scrollIntoView({ block: "nearest" });
  }
}

function handleSuggestionKeyboard(e) {
  if (suggestionsNode.hidden) return;

  const items = suggestionsNode.querySelectorAll(".suggestion-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    state.activeSuggestionIndex = Math.min(state.activeSuggestionIndex + 1, items.length - 1);
    updateSuggestionHighlight();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    state.activeSuggestionIndex = Math.max(state.activeSuggestionIndex - 1, -1);
    updateSuggestionHighlight();
  } else if (e.key === "Enter" && state.activeSuggestionIndex >= 0) {
    e.preventDefault();
    items[state.activeSuggestionIndex].click();
  } else if (e.key === "Escape") {
    hideSuggestions();
  }
}

async function loadSuggestions() {
  const query = symbolInput.value.trim();
  if (!query) { hideSuggestions(); return; }

  if (state.activeSuggestionController) state.activeSuggestionController.abort();
  const currentId = ++state.suggestionRequestId;
  const controller = new AbortController();
  state.activeSuggestionController = controller;

  try {
    const res = await fetch(
      `/api/tickers?query=${encodeURIComponent(query)}&limit=10&asset_type=${encodeURIComponent(currentAssetType())}`,
      { signal: controller.signal },
    );
    const data = await res.json();
    if (currentId !== state.suggestionRequestId) return;
    if (!res.ok) { hideSuggestions(); return; }
    renderSuggestions(data.tickers || []);
  } catch (e) {
    if (e?.name !== "AbortError" && currentId === state.suggestionRequestId) hideSuggestions();
  }
}

function queueSuggestionsLoad() {
  clearTimeout(state.suggestionTimer);
  state.suggestionTimer = setTimeout(loadSuggestions, 150);
}

// =============================================
// TOP ASSETS
// =============================================
function renderTopAssets(items) {
  topAssetsNode.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    topAssetsNode.innerHTML = '<p class="empty-hint">No trending assets available.</p>';
    return;
  }

  for (const item of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn";
    btn.title = `${item.symbol} - ${item.name}`;
    btn.innerHTML = `<span class="chip-symbol">${item.symbol}</span><span class="chip-name">${item.name}</span>`;
    btn.addEventListener("click", () => {
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });
    topAssetsNode.appendChild(btn);
  }
}

async function loadTopAssets() {
  topAssetsNode.innerHTML = `
    <div class="skeleton-chips">
      <div class="skeleton-chip"></div><div class="skeleton-chip"></div>
      <div class="skeleton-chip"></div><div class="skeleton-chip"></div>
      <div class="skeleton-chip"></div><div class="skeleton-chip"></div>
    </div>`;

  const currentId = ++state.topAssetsRequestId;
  if (state.activeTopAssetsController) state.activeTopAssetsController.abort();
  const controller = new AbortController();
  state.activeTopAssetsController = controller;

  try {
    const res = await fetch(
      `/api/top-assets?limit=10&asset_type=${encodeURIComponent(currentAssetType())}`,
      { signal: controller.signal },
    );
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    if (currentId !== state.topAssetsRequestId) return;
    if (!res.ok) {
      topAssetsNode.innerHTML = `<p class="empty-hint">${formatApiError(data, "Could not load trending assets.")}</p>`;
      return;
    }
    renderTopAssets(data?.items || []);
  } catch (e) {
    if (e?.name === "AbortError" || currentId !== state.topAssetsRequestId) return;
    topAssetsNode.innerHTML = '<p class="empty-hint">Could not load trending assets.</p>';
  }
}

// =============================================
// WATCHLIST (localStorage)
// =============================================
const WATCHLIST_KEY = "aurion-watchlist";

function getWatchlist() {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveWatchlist(list) {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
}

function addToWatchlist(symbol, assetType) {
  const list = getWatchlist();
  if (list.some((item) => item.symbol === symbol)) return;
  list.push({ symbol, asset_type: assetType });
  saveWatchlist(list);
  renderWatchlist();
}

function removeFromWatchlist(symbol) {
  const list = getWatchlist().filter((item) => item.symbol !== symbol);
  saveWatchlist(list);
  renderWatchlist();
}

function renderWatchlist() {
  const list = getWatchlist();
  watchlistItems.innerHTML = "";

  if (list.length === 0) {
    watchlistItems.innerHTML = '<p class="empty-hint">No symbols saved yet. Generate a forecast and click + to add.</p>';
    return;
  }

  for (const item of list) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn watchlist-chip";
    btn.innerHTML = `
      <div>
        <span class="chip-symbol">${item.symbol}</span>
        <span class="chip-name">${item.asset_type}</span>
      </div>
      <span class="chip-remove" title="Remove">&times;</span>
    `;

    // Click the chip area (not the remove button) to load the symbol
    btn.addEventListener("click", (e) => {
      if (e.target.closest(".chip-remove")) {
        e.stopPropagation();
        removeFromWatchlist(item.symbol);
        return;
      }
      // Set asset type
      const segBtns = assetTypeControl.querySelectorAll(".seg-btn");
      segBtns.forEach((b) => {
        b.classList.toggle("active", b.dataset.value === item.asset_type);
      });
      assetTypeInput.value = item.asset_type;
      applyAssetTypeUi();

      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });

    watchlistItems.appendChild(btn);
  }
}

// =============================================
// CHART
// =============================================
function buildDatasets(history, forecast) {
  const historyDates = history.map((r) => r.date);
  const forecastDates = forecast.map((r) => r.date);
  const labels = [...historyDates, ...forecastDates];

  const historyPrices = history.map((r) => r.close);
  const historyData = [...historyPrices, ...Array(forecast.length).fill(null)];
  const lastPrice = historyPrices[historyPrices.length - 1];

  const forecastLine = [
    ...Array(history.length - 1).fill(null),
    lastPrice,
    ...forecast.map((r) => r.predicted),
  ];

  const lowerBand = [...Array(history.length - 1).fill(null), lastPrice, ...forecast.map((r) => r.lower)];
  const upperBand = [...Array(history.length - 1).fill(null), lastPrice, ...forecast.map((r) => r.upper)];

  return { labels, historyData, forecastLine, lowerBand, upperBand };
}

function renderChart(data) {
  if (typeof window.Chart !== "function") {
    throw new Error("Chart library not loaded. Please reload the page.");
  }

  const ctx = chartCanvas.getContext("2d");
  const colors = getChartColors();
  const { labels, historyData, forecastLine, lowerBand, upperBand } = buildDatasets(data.history, data.forecast);

  const config = {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Historical",
          data: historyData,
          borderColor: colors.history,
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
          order: 2,
        },
        {
          label: "Forecast",
          data: forecastLine,
          borderColor: colors.forecast,
          borderWidth: 2.5,
          borderDash: [6, 4],
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
          order: 1,
        },
        {
          label: "Confidence Band",
          data: upperBand,
          borderColor: "transparent",
          backgroundColor: colors.band,
          fill: "+1",
          tension: 0.3,
          pointRadius: 0,
          order: 3,
        },
        {
          label: "_lower",
          data: lowerBand,
          borderColor: "transparent",
          backgroundColor: "transparent",
          tension: 0.3,
          pointRadius: 0,
          order: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, color: colors.text, font: { size: 11 } },
          grid: { color: colors.grid },
          border: { display: false },
        },
        y: {
          ticks: { color: colors.text, font: { size: 11 } },
          grid: { color: colors.grid },
          border: { display: false },
        },
      },
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: {
            color: colors.text,
            usePointStyle: true,
            pointStyle: "circle",
            padding: 16,
            font: { size: 11 },
            filter: (item) => !item.text.startsWith("_"),
          },
        },
        tooltip: {
          backgroundColor: "rgba(0,0,0,0.85)",
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          padding: 12,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label?.startsWith("_")) return null;
              if (ctx.dataset.label === "Confidence Band") return null;
              const val = ctx.parsed.y;
              if (val === null) return null;
              return `${ctx.dataset.label}: ${val.toFixed(2)}`;
            },
            afterBody: (items) => {
              if (!items.length) return "";
              const idx = items[0].dataIndex;
              const upper = upperBand[idx];
              const lower = lowerBand[idx];
              if (upper != null && lower != null) {
                return `Band: ${lower.toFixed(2)} \u2013 ${upper.toFixed(2)}`;
              }
              return "";
            },
          },
        },
      },
      animation: { duration: 600, easing: "easeOutCubic" },
    },
  };

  if (state.chart) state.chart.destroy();
  state.chart = new window.Chart(ctx, config);
}

// =============================================
// SIGNAL CARD
// =============================================
function updateSignalCard(data) {
  signalCard.hidden = false;
  disclaimerBanner.hidden = false;
  state.lastPrediction = data;

  const summary = data.summary;
  const signalLabels = {
    bullish: "Bullish Outlook",
    mildly_bullish: "Mildly Bullish",
    neutral: "Neutral",
    mildly_bearish: "Mildly Bearish",
    bearish: "Bearish Outlook",
  };
  signalBadge.textContent = signalLabels[summary.signal] || summary.signal;
  signalBadge.setAttribute("data-signal", summary.signal);

  signalSymbol.textContent = data.symbol;
  signalEngine.textContent = `${data.model_name} | ${data.engine_used.toUpperCase()}`;

  // Currency tag
  currencyTag.textContent = data.currency || "USD";

  metricPrice.textContent = formatCurrency(data.stats.last_close, data.currency);
  metricExpected.textContent = formatCurrency(summary.expected_price, data.currency);

  metricReturn.textContent = formatPercent(summary.expected_return_pct);
  metricReturn.className = `metric-value ${summary.expected_return_pct >= 0 ? "positive" : "negative"}`;

  metricTrend.textContent = summary.trend.charAt(0).toUpperCase() + summary.trend.slice(1);
  metricTrend.className = `metric-value ${summary.trend === "bullish" ? "positive" : summary.trend === "bearish" ? "negative" : ""}`;

  // Confidence tier readout
  const tier = summary.confidence_tier || "low";
  const tierWidths = { low: "30%", medium: "60%", high: "90%" };
  const tierLabels = { low: "Low", medium: "Medium", high: "High" };
  confidenceFill.style.width = tierWidths[tier] || "30%";
<<<<<<< claude/zealous-kapitsa
  confidenceValue.textContent = tierLabels[tier] || tier;
=======
  confidenceValue.textContent = `${tierLabels[tier] || tier} confidence`;
>>>>>>> main
  confidenceFill.setAttribute("data-level", tier);

  // Evaluation metrics
  if (data.evaluation) {
    evalRow.hidden = false;
    evalMae.textContent = `MAE: ${data.evaluation.mae != null ? data.evaluation.mae.toFixed(2) : "-"}`;
    evalDir.textContent = `Dir: ${data.evaluation.directional_accuracy != null ? (data.evaluation.directional_accuracy * 100).toFixed(0) + "%" : "-"}`;
    evalMape.textContent = `MAPE: ${data.evaluation.mape != null ? data.evaluation.mape.toFixed(1) + "%" : "-"}`;
  } else {
    evalRow.hidden = true;
  }

  // Source & degradation
  sourceBadgeNode.hidden = false;
  sourceBadgeNode.textContent = `${data.source.market_data} / ${data.source.forecast}`;

  if (data.degraded) {
    degradedBadgeNode.hidden = false;
    degradedBadgeNode.textContent = data.degradation_message
      ? `Using statistical fallback \u2014 ${data.degradation_message}`
      : "Using statistical fallback";
  } else {
    degradedBadgeNode.hidden = true;
  }

  // Disclaimer
  disclaimerNode.hidden = false;
  disclaimerNode.textContent = `${data.disclaimer} ${data.engine_note || ""}`.trim();

  // Show watchlist add button
  watchlistAddBtn.hidden = false;

  // Explanation card
  if (data.explanation && data.explanation.top_features?.length > 0) {
    explanationCard.hidden = false;
    explanationSource.textContent = `Forecast source: ${formatSourceLabel(data.source.forecast)}. Explanation source: ${formatSourceLabel(data.source.analysis)}.`;
    if (data.source.analysis && data.source.analysis !== data.source.forecast) {
      explanationNote.hidden = false;
      explanationNote.textContent = "Final forecast uses the statistical fallback. This explanation summarizes how the current market pattern differed from the ML analog set before the quality gate rejected the forecast.";
    } else {
      explanationNote.hidden = true;
      explanationNote.textContent = "";
    }
    explanationNarrative.textContent = data.explanation.narrative || "";

<<<<<<< claude/zealous-kapitsa
    // Render feature bars (DOM API — no innerHTML to avoid XSS)
    explanationFeatures.replaceChildren();
    const maxContrib = Math.max(...data.explanation.top_features.map((f) => f.contribution), 0.01);
    for (const feat of data.explanation.top_features) {
      const barPct = Math.round((feat.contribution / maxContrib) * 100);
      const dirClass = feat.direction === "bullish" ? "positive" : feat.direction === "bearish" ? "negative" : "";

      const nameSpan = document.createElement("span");
      nameSpan.className = "explain-feature-name";
      nameSpan.textContent = feat.feature.replace(/_/g, " ");

      const barFill = document.createElement("div");
      barFill.className = `explain-bar-fill ${dirClass}`.trim();
      barFill.style.width = `${barPct}%`;

      const barTrack = document.createElement("div");
      barTrack.className = "explain-bar-track";
      barTrack.appendChild(barFill);

      const dirSpan = document.createElement("span");
      dirSpan.className = `explain-feature-dir ${dirClass}`.trim();
      dirSpan.textContent = feat.direction;

      const row = document.createElement("div");
      row.className = "explain-feature";
      row.appendChild(nameSpan);
      row.appendChild(barTrack);
      row.appendChild(dirSpan);
=======
    // Render feature bars
    explanationFeatures.innerHTML = "";
    const maxContrib = Math.max(...data.explanation.top_features.map((f) => f.difference_score), 0.01);
    for (const feat of data.explanation.top_features) {
      const barPct = Math.round((feat.difference_score / maxContrib) * 100);
      const dirClass = feat.relation === "higher" ? "positive" : feat.relation === "lower" ? "negative" : "";
      const row = document.createElement("div");
      row.className = "explain-feature";
      row.innerHTML = `
        <span class="explain-feature-name">${feat.feature.replace(/_/g, " ")}</span>
        <div class="explain-bar-track">
          <div class="explain-bar-fill ${dirClass}" style="width: ${barPct}%"></div>
        </div>
        <span class="explain-feature-dir ${dirClass}">${feat.relation}</span>
      `;
>>>>>>> main
      explanationFeatures.appendChild(row);
    }

    explanationAnalog.textContent = data.explanation.nearest_analog_date
      ? `Nearest analog: ${data.explanation.nearest_analog_date}`
      : "";
  } else {
    explanationCard.hidden = true;
    explanationSource.textContent = "";
    explanationNote.hidden = true;
    explanationNote.textContent = "";
  }
}

// =============================================
// PREDICTION
// =============================================
function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function deriveSummaryTrend(expectedReturnPct) {
  if (expectedReturnPct > 2) return "bullish";
  if (expectedReturnPct < -2) return "bearish";
  return "neutral";
}

function normalizePredictResponse(payload) {
  const history = Array.isArray(payload?.history) ? payload.history : [];
  const forecast = Array.isArray(payload?.forecast) ? payload.forecast : [];
  const stats = payload?.stats || {};
  const lastClose = isFiniteNumber(stats.last_close) ? stats.last_close : 0;
  const finalPredicted = forecast.length > 0 && isFiniteNumber(forecast[forecast.length - 1]?.predicted)
    ? forecast[forecast.length - 1].predicted
    : lastClose;
  const summary = payload?.summary || {};
  const expectedPrice = isFiniteNumber(summary.expected_price) ? summary.expected_price : finalPredicted;
  const expectedReturnPct = isFiniteNumber(summary.expected_return_pct)
    ? summary.expected_return_pct
    : lastClose > 0 ? ((expectedPrice / lastClose) - 1) * 100 : 0;
  const degradationMessage = payload?.degradation_message ?? payload?.degradation_reason ?? null;
  const allowedTiers = new Set(["low", "medium", "high"]);
  const allowedTrends = new Set(["bullish", "bearish", "neutral"]);
  const allowedSignals = new Set(["bullish", "mildly_bullish", "neutral", "mildly_bearish", "bearish"]);
  const allowedRelations = new Set(["higher", "lower", "similar"]);
  const explanationPayload = payload?.explanation;
  const normalizedExplanation = explanationPayload && typeof explanationPayload === "object"
    ? {
        ...explanationPayload,
        top_features: Array.isArray(explanationPayload.top_features)
          ? explanationPayload.top_features.map((feature) => ({
              ...feature,
              difference_score: isFiniteNumber(feature?.difference_score)
                ? feature.difference_score
                : 0,
              relation: allowedRelations.has(feature?.relation) ? feature.relation : "similar",
            }))
          : [],
      }
    : null;

  return {
    ...payload,
    history,
    forecast,
    stats: {
      daily_trend_pct: isFiniteNumber(stats.daily_trend_pct) ? stats.daily_trend_pct : 0,
      last_close: lastClose,
    },
    source: {
      market_data: payload?.source?.market_data || "unknown",
      forecast: payload?.source?.forecast || "unknown",
      analysis: payload?.source?.analysis ?? null,
      data_quality: payload?.source?.data_quality || "clean",
      data_warnings: Array.isArray(payload?.source?.data_warnings) ? payload.source.data_warnings : [],
      stale: Boolean(payload?.source?.stale),
    },
    degraded: Boolean(payload?.degraded),
    degradation_code: payload?.degradation_code ?? null,
    degradation_message: degradationMessage,
    degradation_reason: degradationMessage,
    evaluation: payload?.evaluation ?? null,
    explanation: normalizedExplanation,
    summary: {
      expected_price: expectedPrice,
      expected_return_pct: expectedReturnPct,
      trend: allowedTrends.has(summary.trend) ? summary.trend : deriveSummaryTrend(expectedReturnPct),
      confidence_tier: allowedTiers.has(summary.confidence_tier) ? summary.confidence_tier : "low",
      signal: allowedSignals.has(summary.signal) ? summary.signal : "neutral",
    },
  };
}

async function fetchPrediction(payload, controller) {
  const res = await fetch("/api/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    signal: controller.signal,
  });

  let data = null;
  try { data = await res.json(); } catch { data = null; }

  if (!res.ok) {
    const error = new Error(formatApiError(data, "Error fetching prediction data."));
    error.isApiError = true;
    error.statusCode = res.status;
    throw error;
  }
  return normalizePredictResponse(data);
}

async function loadPrediction(event) {
  event.preventDefault();

  const symbol = symbolInput.value.trim().toUpperCase();
  const horizon = Number.parseInt(horizonInput.value, 10);
  const engine = engineInput.value;
  const assetType = currentAssetType();

  if (!symbol) {
    clearResults();
    setStatus("Please enter a ticker symbol.", true);
    return;
  }

  symbolInput.value = symbol;
  hideSuggestions();
  clearResults();
  // Show skeleton loaders while fetching
  signalCard.hidden = false;
  signalCard.classList.add("skeleton-loading");
  setLoading(true);
  setStatus(`Analyzing ${symbol}...`);

  if (state.activePredictionController) state.activePredictionController.abort();
  const controller = new AbortController();
  state.activePredictionController = controller;
  const currentId = ++state.predictionRequestId;

  try {
    const data = await fetchPrediction({ symbol, horizon, engine, asset_type: assetType }, controller);
    if (currentId !== state.predictionRequestId) return;

    try {
      signalCard.classList.remove("skeleton-loading");
      chartEmpty.hidden = true;
      chartCanvas.hidden = false;
      chartHeader.hidden = false;
      chartTitle.textContent = `${data.symbol} Price Forecast`;
      chartSubtitle.textContent = `${data.horizon_days}d | ${data.engine_used.toUpperCase()} | ${data.currency}`;

      renderChart(data);
      updateSignalCard(data);
    } catch (renderError) {
      clearResults();
      chartFallbackNode.hidden = false;
      chartFallbackNode.textContent = renderError.message || "Chart render failed.";
      setStatus(chartFallbackNode.textContent, true);
      return;
    }

    const assetLabel = data.asset_type === "crypto" ? "crypto" : "stock";
    if (data.degraded) {
      setStatus(`Forecast loaded for ${data.symbol} (${assetLabel}) with fallback.`);
    } else {
      setStatus(`Forecast loaded for ${data.symbol} (${assetLabel}, ${data.engine_used}).`);
    }
  } catch (error) {
    if (error?.name === "AbortError" || currentId !== state.predictionRequestId) return;
    clearResults();
    setStatus(error?.message || "Network error: cannot reach the API.", true);
  } finally {
    if (currentId === state.predictionRequestId) setLoading(false);
  }
}

// =============================================
// EVENT LISTENERS
// =============================================
form.addEventListener("submit", loadPrediction);
symbolInput.addEventListener("input", queueSuggestionsLoad);
symbolInput.addEventListener("focus", queueSuggestionsLoad);
symbolInput.addEventListener("keydown", handleSuggestionKeyboard);
document.addEventListener("click", (e) => { if (!e.target.closest(".autocomplete-wrap")) hideSuggestions(); });
themeToggle.addEventListener("click", toggleTheme);

// Explanation toggle
explanationToggle.addEventListener("click", () => {
  const body = document.getElementById("explanation-body");
  const isOpen = !body.hidden;
  body.hidden = isOpen;
  explanationToggle.setAttribute("aria-expanded", String(!isOpen));
});

// Watchlist add
watchlistAddBtn.addEventListener("click", () => {
  if (state.lastPrediction) {
    addToWatchlist(state.lastPrediction.symbol, state.lastPrediction.asset_type);
    setStatus(`${state.lastPrediction.symbol} added to watchlist.`);
  }
});

// Service Worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// =============================================
// INIT
// =============================================
initTheme();
initSegmentedControls();
initHorizon();
applyAssetTypeUi();
loadTopAssets();
renderWatchlist();
