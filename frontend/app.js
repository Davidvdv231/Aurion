/* ============================================
   AURION - Market Intelligence
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
const dataWarningsNode = document.getElementById("data-warnings");

// Explanation card
const explanationCard = document.getElementById("explanation-card");
const explanationSource = document.getElementById("explanation-source");
const explanationNote = document.getElementById("explanation-note");
const explanationNarrative = document.getElementById("explanation-narrative");
const explanationFeatures = document.getElementById("explanation-features");
const explanationAnalog = document.getElementById("explanation-analog");
const explanationToggle = document.getElementById("explanation-toggle");

const resultsNode = document.getElementById("results");
const heroHorizon = document.getElementById("hero-horizon");
const evalWindows = document.getElementById("eval-windows");
const evalNoChange = document.getElementById("eval-no-change");
const evalBeats = document.getElementById("eval-beats");
const evalNote = document.getElementById("eval-note");

// Chart
const chartFigure = document.getElementById("chart-figure");
const chartTitle = document.getElementById("chart-title");
const chartSubtitle = document.getElementById("chart-subtitle");
const chartEmpty = document.getElementById("chart-empty");
const chartCanvas = document.getElementById("stock-chart");
const chartTooltip = document.getElementById("chart-tooltip");
const rangeControl = document.getElementById("range-control");
const forecastTableBody = document.getElementById("forecast-table-body");
const chartFallbackNode = document.getElementById("chart-fallback");
const disclaimerNode = document.getElementById("disclaimer");

// Theme
const themeToggle = document.getElementById("theme-toggle");
const themeIconDark = document.getElementById("theme-icon-dark");
const themeIconLight = document.getElementById("theme-icon-light");

// Currency
const currencySelect = document.getElementById("display-currency");

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
  chartRange: "6m",
};

// =============================================
// THEME
// =============================================
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

// Preferences fall back to memory when browser storage is blocked or full, so the
// current visit keeps working; writePreference reports whether the value persisted.
const volatilePreferences = new Map();

function readPreference(key) {
  if (volatilePreferences.has(key)) return volatilePreferences.get(key);
  try { return localStorage.getItem(key); } catch { return null; }
}

function writePreference(key, value) {
  volatilePreferences.set(key, value);
  try { localStorage.setItem(key, value); return true; } catch { return false; }
}

function readSavedTheme() {
  const saved = readPreference("aurion-theme");
  return saved === "light" || saved === "dark" ? saved : null;
}

function effectiveTheme() {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "light" || explicit === "dark") return explicit;
  return prefersDark.matches ? "dark" : "light";
}

function initTheme() {
  const saved = readSavedTheme();
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcons(effectiveTheme());
  prefersDark.addEventListener("change", () => {
    if (readSavedTheme()) return;
    updateThemeIcons(effectiveTheme());
    rerenderChart();
  });
}

function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  writePreference("aurion-theme", next);
  updateThemeIcons(next);
  rerenderChart();
}

// =============================================
// CURRENCY PREFERENCE
// =============================================
function initCurrency() {
  const saved = readPreference("aurion-currency");
  if (Array.from(currencySelect.options).some((option) => option.value === saved)) {
    currencySelect.value = saved;
  }
  currencySelect.addEventListener("change", () => {
    writePreference("aurion-currency", currencySelect.value);
    invalidatePrediction();
  });
}

function updateThemeIcons(theme) {
  themeIconDark.style.display = theme === "dark" ? "block" : "none";
  themeIconLight.style.display = theme === "light" ? "block" : "none";
}

function getChartColors() {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(name).trim();
  return {
    history: read("--chart-history"),
    forecast: read("--chart-forecast"),
    band: read("--chart-band"),
    grid: read("--chart-grid"),
    rule: read("--chart-rule"),
    surface: read("--surface"),
    text: read("--ink-3"),
    fontFamily: read("--font-sans"),
  };
}

function rerenderChart() {
  if (state.chart && state.lastPrediction) renderChart(state.lastPrediction);
}

// =============================================
// SEGMENTED CONTROLS
// =============================================
function initSegmentedControls() {
  setupSegmented(assetTypeControl, assetTypeInput, () => {
    invalidatePrediction();
    applyAssetTypeUi();
    applyEngineDefault();
    hideSuggestions();
    clearResults();
    loadTopAssets();
  });
  setupSegmented(engineControl, engineInput, invalidatePrediction);
}

function applyEngineDefault() {
  const isCrypto = currentAssetType() === "crypto";
  selectSegment(engineControl, engineInput, isCrypto ? "stat" : "ml");
  if (isCrypto) {
    setStatus("Crypto uses the statistical model by default: the ML model showed no edge on crypto in backtests. You can still pick ML.");
  }
}

function selectSegment(control, hiddenInput, value) {
  control.querySelectorAll(".seg-btn").forEach((b) => {
    const isActive = b.dataset.value === value;
    b.classList.toggle("active", isActive);
    b.setAttribute("aria-pressed", String(isActive));
  });
  hiddenInput.value = value;
}

function setupSegmented(control, hiddenInput, onChange) {
  control.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (hiddenInput.value === btn.dataset.value) return;
      selectSegment(control, hiddenInput, btn.dataset.value);
      if (onChange) onChange(btn.dataset.value);
    });
  });
  // Sync visual and ARIA state with the hidden input, which the markup may not match.
  selectSegment(control, hiddenInput, hiddenInput.value);
}

// =============================================
// HORIZON SLIDER
// =============================================
function formatDays(days) {
  return `${days} ${Number(days) === 1 ? "day" : "days"}`;
}

function initHorizon() {
  horizonInput.addEventListener("input", () => {
    horizonValue.textContent = formatDays(horizonInput.value);
    invalidatePrediction();
  });
}

// =============================================
// HELPERS
// =============================================
function currentAssetType() {
  return assetTypeInput.value === "crypto" ? "crypto" : "stock";
}

function setStatus(message, isError = false) {
  clearTimeout(state.statusTimer);
  statusNode.textContent = message;
  statusNode.className = isError ? "global-status error" : "global-status";
  if (message && !isError) {
    state.statusTimer = setTimeout(() => { statusNode.textContent = ""; }, 5000);
  }
}

function setLoading(isLoading) {
  form.setAttribute("aria-busy", String(isLoading));
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

const CURRENCY_LOCALES = { USD: "en-US", EUR: "de-DE", GBP: "en-GB", JPY: "ja-JP", CHF: "de-CH", CAD: "en-CA", AUD: "en-AU" };

function localeFor(code) {
  return CURRENCY_LOCALES[code] || "en-US";
}

function formatCurrency(value, currency) {
  const code = currency || "USD";
  try {
    return new Intl.NumberFormat(localeFor(code), {
      style: "currency",
      currency: code,
      ...(value > 0 && value < 0.01
        ? { maximumSignificantDigits: 4 }
        : { maximumFractionDigits: code === "JPY" ? 0 : 2 }),
    }).format(value);
  } catch {
    return `${Number.isFinite(value) ? value.toFixed(2) : "0.00"} ${code}`;
  }
}

function formatPercent(value) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatSourceLabel(value) {
  const labels = {
    ml_analog: "ML analog",
    stat: "Statistical baseline",
    stat_fallback: "Statistical fallback",
    ml_pattern_difference: "Pattern-difference analysis",
    unknown: "Unknown",
  };
  return labels[value] || String(value || "Unknown").replace(/_/g, " ");
}

// =============================================
// UI STATE
// =============================================
function hideSuggestions() {
  // Cancel a queued or in-flight lookup too, or its answer reopens the list
  // (e.g. right after a submit).
  clearTimeout(state.suggestionTimer);
  state.suggestionRequestId += 1;
  if (state.activeSuggestionController) state.activeSuggestionController.abort();
  suggestionsNode.hidden = true;
  suggestionsNode.innerHTML = "";
  state.activeSuggestionIndex = -1;
  symbolInput.setAttribute("aria-expanded", "false");
  symbolInput.removeAttribute("aria-activedescendant");
}

function clearResults() {
  resultsNode.classList.remove("is-refreshing");
  dataWarningsNode.hidden = true;
  dataWarningsNode.textContent = "";
  signalCard.hidden = true;
  explanationCard.hidden = true;
  chartFigure.hidden = true;
  chartEmpty.hidden = false;
  chartCanvas.hidden = true;
  chartTooltip.hidden = true;
  forecastTableBody.textContent = "";
  chartFallbackNode.hidden = true;
  disclaimerNode.hidden = true;
  degradedBadgeNode.hidden = true;
  evalRow.hidden = true;
  watchlistAddBtn.hidden = true;
  state.lastPrediction = null;
  if (state.chart) {
    state.chart.destroy();
    state.chart = undefined;
  }
}

function invalidatePrediction() {
  state.activePredictionController?.abort();
  state.predictionRequestId++;
  clearResults();
  setLoading(false);
  setStatus("");
}

function applyAssetTypeUi() {
  const assetType = currentAssetType();
  topTitleNode.textContent = assetType === "crypto" ? "Trending crypto" : "Trending stocks";
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
    li.setAttribute("role", "presentation");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "suggestion-item";
    btn.dataset.index = i;
    btn.id = `ticker-suggestion-${i}`;
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", "false");
    const symSpan = document.createElement("span");
    symSpan.className = "suggestion-symbol";
    symSpan.textContent = item.symbol;
    const nameSpan = document.createElement("span");
    nameSpan.className = "suggestion-name";
    nameSpan.textContent = item.name + " (" + item.exchange + ")";
    btn.appendChild(symSpan);
    btn.appendChild(nameSpan);
    btn.addEventListener("click", () => {
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });
    li.appendChild(btn);
    suggestionsNode.appendChild(li);
  }
  suggestionsNode.hidden = false;
  symbolInput.setAttribute("aria-expanded", "true");
}

function updateSuggestionHighlight() {
  const items = suggestionsNode.querySelectorAll(".suggestion-item");
  items.forEach((item, i) => {
    const isActive = i === state.activeSuggestionIndex;
    item.classList.toggle("active", isActive);
    item.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  if (state.activeSuggestionIndex >= 0 && items[state.activeSuggestionIndex]) {
    const active = items[state.activeSuggestionIndex];
    active.scrollIntoView({ block: "nearest" });
    if (active.id) symbolInput.setAttribute("aria-activedescendant", active.id);
  } else {
    symbolInput.removeAttribute("aria-activedescendant");
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
  // Invalidate in-flight lookups so an answer for older input cannot render, but keep
  // the visible list in place so it does not flicker while typing.
  clearTimeout(state.suggestionTimer);
  state.suggestionRequestId += 1;
  if (state.activeSuggestionController) state.activeSuggestionController.abort();
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
    const chipSym = document.createElement("span");
    chipSym.className = "chip-symbol";
    chipSym.textContent = item.symbol;
    const chipName = document.createElement("span");
    chipName.className = "chip-name";
    chipName.textContent = item.name;
    btn.appendChild(chipSym);
    btn.appendChild(chipName);
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
      topAssetsNode.textContent = "";
      const errP = document.createElement("p");
      errP.className = "empty-hint";
      errP.textContent = formatApiError(data, "Could not load trending assets.");
      topAssetsNode.appendChild(errP);
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
    const raw = readPreference(WATCHLIST_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && typeof item.symbol === "string"
      && /^[A-Z0-9^][A-Z0-9.^=_-]{0,19}$/.test(item.symbol)
      && ["stock", "crypto"].includes(item.asset_type)).slice(0, 100);
  } catch {
    return [];
  }
}

function saveWatchlist(list) {
  const saved = writePreference(WATCHLIST_KEY, JSON.stringify(list));
  if (!saved) {
    setStatus("Browser storage is unavailable. Watchlist changes last for this visit only.", true);
  }
  return saved;
}

function addToWatchlist(symbol, assetType) {
  const list = getWatchlist();
  if (list.some((item) => item.symbol === symbol && item.asset_type === assetType)) return;
  if (list.length >= 100) { setStatus("Your watchlist is full. Remove a symbol first.", true); return; }
  list.push({ symbol, asset_type: assetType });
  const saved = saveWatchlist(list);
  renderWatchlist();
  updateWatchlistButton();
  return saved;
}

function removeFromWatchlist(symbol, assetType) {
  const list = getWatchlist().filter((item) => item.symbol !== symbol || item.asset_type !== assetType);
  saveWatchlist(list);
  renderWatchlist();
  updateWatchlistButton();
}

function renderWatchlist() {
  const list = getWatchlist();
  watchlistItems.innerHTML = "";

  if (list.length === 0) {
    watchlistItems.innerHTML = '<p class="empty-hint">Nothing saved yet.</p>';
    return;
  }

  for (const item of list) {
    const entry = document.createElement("span");
    entry.className = "watchlist-entry";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn";
    const wlSym = document.createElement("span");
    wlSym.className = "chip-symbol";
    wlSym.textContent = item.symbol;
    const wlType = document.createElement("span");
    wlType.className = "chip-name";
    wlType.textContent = item.asset_type === "crypto" ? "crypto" : "stock";
    btn.appendChild(wlSym);
    btn.appendChild(wlType);
    btn.addEventListener("click", () => {
      const nextType = item.asset_type === "crypto" ? "crypto" : "stock";
      const typeChanged = currentAssetType() !== nextType;
      selectSegment(assetTypeControl, assetTypeInput, nextType);
      applyAssetTypeUi();
      if (typeChanged) {
        applyEngineDefault();
        loadTopAssets();
      }
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "chip-remove";
    // The same symbol can be saved once per market, so the label names both.
    removeBtn.setAttribute("aria-label", `Remove ${item.symbol} ${wlType.textContent} from watchlist`);
    removeBtn.title = "Remove";
    removeBtn.textContent = "\u00d7";
    removeBtn.addEventListener("click", () => removeFromWatchlist(item.symbol, item.asset_type));

    entry.appendChild(btn);
    entry.appendChild(removeBtn);
    watchlistItems.appendChild(entry);
  }
}

// =============================================
// CHART
// =============================================
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const RANGE_MONTHS = { "3m": 3, "6m": 6, "1y": 12 };

function sliceHistory(history, range) {
  const months = RANGE_MONTHS[range];
  if (!months || history.length < 2) return history;
  const cutoff = new Date(`${history[history.length - 1].date}T00:00:00Z`);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
  const cutoffIso = cutoff.toISOString().slice(0, 10);
  const sliced = history.filter((row) => row.date >= cutoffIso);
  return sliced.length >= 2 ? sliced : history;
}

function buildDatasets(history, forecast) {
  const labels = [...history.map((r) => r.date), ...forecast.map((r) => r.date)];
  const historyPrices = history.map((r) => r.close);
  const lastPrice = historyPrices[historyPrices.length - 1];
  const lead = Array(history.length - 1).fill(null);

  return {
    labels,
    junction: history.length - 1,
    historyData: [...historyPrices, ...Array(forecast.length).fill(null)],
    forecastLine: [...lead, lastPrice, ...forecast.map((r) => r.predicted)],
    lowerBand: [...lead, lastPrice, ...forecast.map((r) => r.lower)],
    upperBand: [...lead, lastPrice, ...forecast.map((r) => r.upper)],
  };
}

function parseIsoDate(iso) {
  return new Date(`${String(iso).slice(0, 10)}T00:00:00Z`);
}

function formatDate(iso, options) {
  const date = parseIsoDate(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleDateString("en-US", { timeZone: "UTC", ...options });
}

function formatAxisPrice(value, currency) {
  const code = currency || "USD";
  const abs = Math.abs(value);
  try {
    return new Intl.NumberFormat(localeFor(code), {
      style: "currency",
      currency: code,
      notation: abs >= 10000 ? "compact" : "standard",
      minimumFractionDigits: 0,
      maximumFractionDigits: abs >= 100 ? 0 : 2,
    }).format(value);
  } catch {
    return String(value);
  }
}

function renderForecastTable(forecast, currency) {
  forecastTableBody.textContent = "";
  for (const row of forecast) {
    const tr = document.createElement("tr");
    const cells = [
      formatDate(row.date, { month: "short", day: "numeric", year: "numeric" }),
      formatCurrency(row.predicted, currency),
      formatCurrency(row.lower, currency),
      formatCurrency(row.upper, currency),
    ];
    for (const text of cells) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
    forecastTableBody.appendChild(tr);
  }
}

function tooltipRow(keyClass, value, label) {
  const row = document.createElement("div");
  row.className = "tt-row";
  const key = document.createElement("span");
  key.className = `key tt-key ${keyClass}`;
  const valueNode = document.createElement("span");
  valueNode.className = "tt-value";
  valueNode.textContent = value;
  const labelNode = document.createElement("span");
  labelNode.className = "tt-label";
  labelNode.textContent = label;
  row.append(key, valueNode, labelNode);
  return row;
}

function renderTooltip({ chart, tooltip }, view) {
  if (tooltip.opacity === 0 || !tooltip.dataPoints?.length) {
    chartTooltip.hidden = true;
    return;
  }

  const idx = tooltip.dataPoints[0].dataIndex;
  const fmt = (value) => formatCurrency(value, view.currency);
  chartTooltip.textContent = "";

  const title = document.createElement("div");
  title.className = "tt-title";
  title.textContent = formatDate(view.labels[idx], { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  chartTooltip.appendChild(title);

  if (view.historyData[idx] != null) {
    chartTooltip.appendChild(tooltipRow("key--history", fmt(view.historyData[idx]), "Close"));
  }
  if (idx > view.junction && view.forecastLine[idx] != null) {
    chartTooltip.appendChild(tooltipRow("key--forecast", fmt(view.forecastLine[idx]), "Forecast"));
    if (view.lowerBand[idx] != null && view.upperBand[idx] != null) {
      chartTooltip.appendChild(
        tooltipRow("key--band", `${fmt(view.lowerBand[idx])} – ${fmt(view.upperBand[idx])}`, "Range"),
      );
    }
  }

  chartTooltip.hidden = false;
  const gap = 12;
  const width = chartTooltip.offsetWidth;
  let left = tooltip.caretX + gap;
  if (left + width > chart.width) left = tooltip.caretX - gap - width;
  chartTooltip.style.left = `${Math.max(0, left)}px`;
  chartTooltip.style.top = `${chart.chartArea.top}px`;
}

function annotationsPlugin(view, colors) {
  return {
    id: "aurionAnnotations",
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const font = `12px ${colors.fontFamily}`;
      ctx.save();
      ctx.lineWidth = 1;
      ctx.strokeStyle = colors.rule;

      // Where the forecast starts.
      const startX = Math.round(scales.x.getPixelForValue(view.junction)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(startX, chartArea.top);
      ctx.lineTo(startX, chartArea.bottom);
      ctx.stroke();
      ctx.font = font;
      ctx.fillStyle = colors.text;
      ctx.textBaseline = "top";
      if (chartArea.right - startX > 150) ctx.fillText("Forecast →", startX + 6, chartArea.top + 2);

      // Crosshair at the hovered date.
      const active = chart.tooltip?.getActiveElements?.() || [];
      if (active.length) {
        const x = Math.round(active[0].element.x) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();
      }

      // Direct label on the forecast endpoint.
      const points = chart.getDatasetMeta(1).data;
      const end = points[points.length - 1];
      const endValue = view.forecastLine[view.forecastLine.length - 1];
      if (end && endValue != null && view.forecastLine.length - 1 > view.junction) {
        const label = formatCurrency(endValue, view.currency);
        ctx.font = `600 ${font}`;
        ctx.textAlign = "right";
        ctx.textBaseline = "bottom";
        const y = Math.max(end.y - 10, chartArea.top + 16);
        ctx.lineJoin = "round";
        ctx.lineWidth = 4;
        ctx.strokeStyle = colors.surface;
        ctx.strokeText(label, end.x - 8, y);
        ctx.fillStyle = colors.ink;
        ctx.fillText(label, end.x - 8, y);
      }
      ctx.restore();
    },
  };
}

function renderChart(data) {
  if (typeof window.Chart !== "function") {
    throw new Error("Chart library not loaded. Please reload the page.");
  }

  const colors = getChartColors();
  colors.ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim();
  const currency = data.display_currency || data.currency || "USD";
  const history = sliceHistory(data.history, state.chartRange);
  const view = { ...buildDatasets(history, data.forecast), currency };
  const lastIndex = view.labels.length - 1;
  const spanDays = view.labels.length > 1
    ? (parseIsoDate(view.labels[lastIndex]) - parseIsoDate(view.labels[0])) / 86400000
    : 0;
  const tickFormat = spanDays > 240 ? { month: "short", year: "numeric" } : { month: "short", day: "numeric" };

  window.Chart.defaults.font.family = colors.fontFamily;
  const endDot = (index) => (ctx) => (ctx.dataIndex === index ? 4 : 0);
  const pointStyle = (color) => ({
    pointBackgroundColor: color,
    pointBorderColor: colors.surface,
    pointBorderWidth: 2,
    pointHoverRadius: 4,
    pointHoverBackgroundColor: color,
    pointHoverBorderColor: colors.surface,
    pointHoverBorderWidth: 2,
  });

  const config = {
    type: "line",
    data: {
      labels: view.labels,
      datasets: [
        {
          label: "Daily close",
          data: view.historyData,
          borderColor: colors.history,
          borderWidth: 2,
          borderJoinStyle: "round",
          borderCapStyle: "round",
          tension: 0,
          pointRadius: endDot(view.junction),
          ...pointStyle(colors.history),
          order: 2,
        },
        {
          label: "Forecast",
          data: view.forecastLine,
          borderColor: colors.forecast,
          borderWidth: 2,
          borderDash: [6, 4],
          borderJoinStyle: "round",
          tension: 0,
          pointRadius: endDot(lastIndex),
          ...pointStyle(colors.forecast),
          order: 1,
        },
        {
          label: "Forecast range",
          data: view.upperBand,
          borderColor: "transparent",
          backgroundColor: colors.band,
          fill: "+1",
          tension: 0,
          pointRadius: 0,
          pointHoverRadius: 0,
          order: 3,
        },
        {
          label: "_lower",
          data: view.lowerBand,
          borderColor: "transparent",
          backgroundColor: "transparent",
          tension: 0,
          pointRadius: 0,
          pointHoverRadius: 0,
          order: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 18, right: 4 } },
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          ticks: {
            color: colors.text,
            maxRotation: 0,
            autoSkip: true,
            autoSkipPadding: 28,
            font: { size: 12 },
            callback(value) {
              return formatDate(this.getLabelForValue(value), tickFormat);
            },
          },
          grid: { display: false },
          border: { display: true, color: colors.rule },
        },
        y: {
          position: "right",
          ticks: {
            color: colors.text,
            maxTicksLimit: 6,
            font: { size: 12 },
            callback: (value) => formatAxisPrice(value, currency),
          },
          grid: { color: colors.grid, lineWidth: 1 },
          border: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false, external: (context) => renderTooltip(context, view) },
      },
      animation: reducedMotion.matches ? false : { duration: 300, easing: "easeOutCubic" },
    },
    plugins: [annotationsPlugin(view, colors)],
  };

  if (state.chart) state.chart.destroy();
  chartTooltip.hidden = true;
  state.chart = new window.Chart(chartCanvas.getContext("2d"), config);
}

// =============================================
// SIGNAL CARD
// =============================================
const FEATURE_ACRONYMS = new Set(["sma", "ema", "rsi", "macd", "bb"]);

function formatFeatureName(raw) {
  const text = String(raw || "")
    .split("_")
    .map((word) => (FEATURE_ACRONYMS.has(word.toLowerCase()) ? word.toUpperCase() : word))
    .join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function sentenceCase(text) {
  const value = String(text || "");
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function formatDelta(pct) {
  if (pct > 0) return { text: `▲ ${formatPercent(pct)}`, tone: "up" };
  if (pct < 0) return { text: `▼ ${formatPercent(pct)}`, tone: "down" };
  return { text: `▬ ${formatPercent(pct)}`, tone: "" };
}

function updateWatchlistButton() {
  const prediction = state.lastPrediction;
  if (!prediction) {
    watchlistAddBtn.hidden = true;
    return;
  }
  const saved = getWatchlist().some(
    (item) => item.symbol === prediction.symbol && item.asset_type === prediction.asset_type,
  );
  watchlistAddBtn.hidden = false;
  watchlistAddBtn.disabled = saved;
  watchlistAddBtn.textContent = saved ? "In your watchlist" : "Add to watchlist";
}

function renderExplanation(data) {
  if (!data.explanation || !(data.explanation.top_features?.length > 0)) {
    explanationCard.hidden = true;
    explanationSource.textContent = "";
    explanationNote.hidden = true;
    explanationNote.textContent = "";
    return;
  }

  explanationCard.hidden = false;
  explanationSource.textContent = `Forecast source: ${formatSourceLabel(data.source.forecast)}. Explanation source: ${formatSourceLabel(data.source.analysis)}.`;
  if (data.source.forecast === "stat_fallback" && data.source.analysis) {
    explanationNote.hidden = false;
    explanationNote.textContent = "Final forecast uses the statistical fallback. This explanation summarizes how the current market pattern differed from the ML analog set before the quality gate rejected the forecast.";
  } else {
    explanationNote.hidden = true;
    explanationNote.textContent = "";
  }
  explanationNarrative.textContent = data.explanation.narrative || "";

  explanationFeatures.textContent = "";
  const maxScore = Math.max(...data.explanation.top_features.map((f) => f.difference_score), 0.01);
  for (const feat of data.explanation.top_features) {
    const halfWidthPct = Math.round((feat.difference_score / maxScore) * 50);
    const row = document.createElement("li");
    row.className = "explain-feature";

    const nameSpan = document.createElement("span");
    nameSpan.className = "explain-feature-name";
    nameSpan.textContent = formatFeatureName(feat.feature);
    nameSpan.title = nameSpan.textContent;

    const barTrack = document.createElement("span");
    barTrack.className = "explain-bar-track";
    const barFill = document.createElement("span");
    barFill.className = `explain-bar-fill ${feat.relation}`;
    barFill.style.width = `${Math.max(halfWidthPct, 1)}%`;
    barTrack.appendChild(barFill);

    const dirSpan = document.createElement("span");
    dirSpan.className = "explain-feature-dir";
    dirSpan.textContent = feat.relation;

    row.append(nameSpan, barTrack, dirSpan);
    explanationFeatures.appendChild(row);
  }

  explanationAnalog.textContent = data.explanation.nearest_analog_date
    ? `Nearest analog: ${formatDate(data.explanation.nearest_analog_date, { month: "short", day: "numeric", year: "numeric" })}`
    : "";
}

function updateSignalCard(data) {
  signalCard.hidden = false;
  state.lastPrediction = data;

  const summary = data.summary;
  const displayCurrency = data.display_currency || data.currency || "USD";

  signalSymbol.textContent = data.symbol;
  signalEngine.textContent = `${data.model_name} · ${data.asset_type === "crypto" ? "Crypto" : "Stock"}`;

  heroHorizon.textContent = formatDays(data.horizon_days);
  metricExpected.textContent = formatCurrency(summary.expected_price, displayCurrency);
  const delta = formatDelta(summary.expected_return_pct);
  metricReturn.textContent = delta.text;
  metricReturn.className = `delta ${delta.tone}`.trim();
  metricPrice.textContent = formatCurrency(data.stats.last_close, displayCurrency);
  currencyTag.textContent = displayCurrency;

  signalBadge.textContent = sentenceCase(summary.signal);
  signalBadge.setAttribute("data-signal", summary.signal);
  metricTrend.textContent = sentenceCase(summary.trend);

  const tier = summary.confidence_tier || "low";
  const tierLabels = { low: "Low", medium: "Medium", high: "High" };
  confidenceFill.setAttribute("data-level", tier);
  confidenceValue.textContent = tierLabels[tier] || tier;

  sourceBadgeNode.textContent = `${data.source.market_data} / ${data.source.forecast}`;

  const warnings = (data.source.data_warnings || []).filter((value) => typeof value === "string");
  if (data.source.stale) warnings.unshift("Market data may be stale.");
  dataWarningsNode.textContent = warnings.join(" ");
  dataWarningsNode.hidden = warnings.length === 0;

  if (data.degraded) {
    degradedBadgeNode.hidden = false;
    degradedBadgeNode.textContent = "";
    const lead = document.createElement("strong");
    lead.textContent = "Statistical fallback in use.";
    degradedBadgeNode.appendChild(lead);
    degradedBadgeNode.append(
      ` ${data.degradation_message || "The ML model did not pass its quality gate, so this is the statistical baseline."}`,
    );
  } else {
    degradedBadgeNode.hidden = true;
  }

  if (data.evaluation) {
    const ev = data.evaluation;
    evalRow.hidden = false;
    evalDir.textContent = ev.directional_accuracy != null ? `${(ev.directional_accuracy * 100).toFixed(0)}%` : "-";
    // MAE is in price units; formatCurrency keeps sub-cent errors from reading as 0.00.
    evalMae.textContent = ev.mae != null ? formatCurrency(ev.mae, displayCurrency) : "-";
    // Two decimals: the forecast and the no-change guess often differ by less than 0.1 point.
    evalMape.textContent = ev.mape != null ? `${ev.mape.toFixed(2)}%` : "-";
    evalWindows.textContent = ev.validation_windows != null ? String(ev.validation_windows) : "-";
    evalNoChange.textContent = ev.no_change_mape != null ? `${ev.no_change_mape.toFixed(2)}%` : "-";
    evalBeats.textContent = ev.beats_no_change === true ? "Yes" : ev.beats_no_change === false ? "No" : "-";
    evalNote.hidden = ev.beats_no_change !== false;
  } else {
    evalRow.hidden = true;
  }

  disclaimerNode.hidden = false;
  disclaimerNode.textContent = `${data.disclaimer || ""} ${data.engine_note || ""}`.trim();

  updateWatchlistButton();
  renderExplanation(data);
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

const ALLOWED_ENGINE_USED = new Set(["stat", "ml", "stat_fallback"]);

function normalizePredictResponse(payload) {
  const positive = (value) => isFiniteNumber(value) && value > 0;
  if (!payload || typeof payload.symbol !== "string" || !payload.symbol
      || !positive(payload.stats?.last_close)
      || !Array.isArray(payload.forecast) || payload.forecast.length === 0
      || !payload.forecast.every((point) => point && typeof point.date === "string"
        && [point.predicted, point.lower, point.upper].every(positive) && point.lower <= point.upper)
      || (Array.isArray(payload.history) && !payload.history.every((point) => point && typeof point.date === "string" && positive(point.close)))) {
    throw new Error("The API returned invalid forecast data. Please try again.");
  }
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
  const allowedSignals = new Set(["Strongly Bullish", "Bullish Outlook", "Neutral", "Bearish Outlook", "Strongly Bearish"]);
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

  const engineUsed = ALLOWED_ENGINE_USED.has(payload?.engine_used) ? payload.engine_used : "stat";
  const engineRequested = payload?.engine_requested === "ml" ? "ml" : "stat";
  const horizonDays = Number.isFinite(Number(payload?.horizon_days))
    ? Number(payload.horizon_days)
    : forecast.length;

  return {
    ...payload,
    history,
    forecast,
    horizon_days: horizonDays,
    engine_used: engineUsed,
    engine_requested: engineRequested,
    model_name: typeof payload?.model_name === "string" && payload.model_name ? payload.model_name : "Unknown model",
    currency: typeof payload?.currency === "string" && payload.currency ? payload.currency : "USD",
    symbol: typeof payload?.symbol === "string" && payload.symbol ? payload.symbol : "",
    disclaimer: typeof payload?.disclaimer === "string" ? payload.disclaimer : "",
    engine_note: typeof payload?.engine_note === "string" ? payload.engine_note : "",
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
      signal: allowedSignals.has(summary.signal) ? summary.signal : "Neutral",
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
  if (state.lastPrediction) {
    resultsNode.classList.add("is-refreshing");
    chartFallbackNode.hidden = true;
  } else {
    clearResults();
  }
  setLoading(true);
  setStatus(`Running the forecast for ${symbol}…`);

  if (state.activePredictionController) state.activePredictionController.abort();
  const controller = new AbortController();
  state.activePredictionController = controller;
  const currentId = ++state.predictionRequestId;
  const timeout = setTimeout(() => controller.abort("timeout"), 90_000);

  try {
    const data = await fetchPrediction({ symbol, horizon, engine, asset_type: assetType, display_currency: currencySelect.value }, controller);
    if (currentId !== state.predictionRequestId) return;

    try {
      const displayCurrency = data.display_currency || data.currency || "USD";
      chartEmpty.hidden = true;
      chartFigure.hidden = false;
      chartCanvas.hidden = false;
      chartTitle.textContent = `${data.symbol} daily close and ${data.horizon_days}-day forecast`;
      chartSubtitle.textContent = `Prices in ${displayCurrency}`;

      renderForecastTable(data.forecast, displayCurrency);
      if (data.history.length > 0) {
        renderChart(data);
      } else {
        // Without history the chart would mislead; the forecast table still stands.
        chartCanvas.hidden = true;
        chartFallbackNode.hidden = false;
        chartFallbackNode.textContent = "No price history is available to chart this forecast.";
      }
      updateSignalCard(data);
      resultsNode.classList.remove("is-refreshing");
    } catch (renderError) {
      clearResults();
      chartFallbackNode.hidden = false;
      chartFallbackNode.textContent = renderError.message || "Chart render failed.";
      setStatus(chartFallbackNode.textContent, true);
      return;
    }

    setStatus(
      data.degraded
        ? `Forecast ready for ${data.symbol}, using the statistical fallback.`
        : `Forecast ready for ${data.symbol}.`,
    );
    // On narrow screens the result sits below the form, out of view.
    if (window.matchMedia("(max-width: 719px)").matches) {
      resultsNode.scrollIntoView({ block: "start", behavior: reducedMotion.matches ? "auto" : "smooth" });
    }
  } catch (error) {
    if (currentId !== state.predictionRequestId) return;
    clearResults();
    setStatus(controller.signal.reason === "timeout" ? "The forecast request timed out. Please try again."
      : error?.message || "Network error: cannot reach the API.", true);
  } finally {
    clearTimeout(timeout);
    if (currentId === state.predictionRequestId) setLoading(false);
  }
}

// =============================================
// EVENT LISTENERS
// =============================================
form.addEventListener("submit", loadPrediction);
symbolInput.addEventListener("input", queueSuggestionsLoad);
symbolInput.addEventListener("input", invalidatePrediction);
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
    if (addToWatchlist(state.lastPrediction.symbol, state.lastPrediction.asset_type)) {
      setStatus(`${state.lastPrediction.symbol} added to watchlist.`);
    }
  }
});

// Chart history range
rangeControl.querySelectorAll(".range-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.chartRange = btn.dataset.range;
    rangeControl.querySelectorAll(".range-btn").forEach((b) => {
      const isActive = b === btn;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-pressed", String(isActive));
    });
    rerenderChart();
  });
});

// Service Worker — prompt-to-refresh on a new version instead of an unconditional
// takeover, so an open forecast stays stable across deploys.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    // Capture the controller state at registration time. On a true first-time
    // install there is no controller; the SW activates and claims this page,
    // which fires controllerchange. Reloading in that case would cause a
    // pointless page flash on the very first visit, so we suppress it.
    const hadControllerAtLoad = Boolean(navigator.serviceWorker.controller);

    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        // Set when the user clicks Reload, so an update accepted later in a first
        // visit still reloads even though the page started without a controller.
        let userAcceptedUpdate = false;

        function showUpdatePrompt(worker) {
          if (!worker) return;
          // Persistent banner-style prompt (NOT the auto-clearing global status,
          // which would hide the message after 5s or get overwritten by the
          // next "Analyzing ..." status update).
          const banner = document.getElementById("sw-update-banner");
          const reloadBtn = document.getElementById("sw-update-reload");
          if (!banner || !reloadBtn) return;
          banner.hidden = false;
          const onClick = () => {
            reloadBtn.disabled = true;
            userAcceptedUpdate = true;
            worker.postMessage({ type: "SKIP_WAITING" });
          };
          reloadBtn.addEventListener("click", onClick, { once: true });
        }

        if (registration.waiting) showUpdatePrompt(registration.waiting);

        registration.addEventListener("updatefound", () => {
          const installing = registration.installing;
          if (!installing) return;
          installing.addEventListener("statechange", () => {
            if (installing.state === "installed" && navigator.serviceWorker.controller) {
              showUpdatePrompt(installing);
            }
          });
        });

        // When the active SW finally changes (user accepted), reload once so
        // every tab is serving the new bundle consistently. Skip on first
        // install (no prior controller) — that change is expected, not an upgrade.
        let reloading = false;
        navigator.serviceWorker.addEventListener("controllerchange", () => {
          if (!hadControllerAtLoad && !userAcceptedUpdate) return;
          if (reloading) return;
          reloading = true;
          window.location.reload();
        });
      })
      .catch(() => {});
  });
}

// =============================================
// INIT
// =============================================
initTheme();
initCurrency();
initSegmentedControls();
initHorizon();
applyAssetTypeUi();
loadTopAssets();
renderWatchlist();
