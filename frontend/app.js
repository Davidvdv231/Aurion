const form = document.getElementById("predict-form");
const symbolInput = document.getElementById("symbol");
const horizonInput = document.getElementById("horizon");
const suggestionsNode = document.getElementById("ticker-suggestions");
const topStocksNode = document.getElementById("top-stocks");

const statusNode = document.getElementById("status");
const statsCard = document.getElementById("stats-card");
const lastCloseNode = document.getElementById("last-close");
const trendNode = document.getElementById("trend");
const modelNameNode = document.getElementById("model-name");
const disclaimerNode = document.getElementById("disclaimer");

let chart;
let suggestionTimer;
let suggestionRequestId = 0;

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.style.color = isError ? "#dc2626" : "#1d4ed8";
}

function hideSuggestions() {
  suggestionsNode.hidden = true;
  suggestionsNode.innerHTML = "";
}

function renderSuggestions(tickers) {
  suggestionsNode.innerHTML = "";

  if (!Array.isArray(tickers) || tickers.length === 0) {
    hideSuggestions();
    return;
  }

  for (const item of tickers) {
    const listItem = document.createElement("li");
    const button = document.createElement("button");
    const symbolSpan = document.createElement("span");
    const nameSpan = document.createElement("span");

    button.type = "button";
    button.className = "suggestion-item";

    symbolSpan.className = "suggestion-symbol";
    symbolSpan.textContent = item.symbol;

    nameSpan.className = "suggestion-name";
    nameSpan.textContent = `${item.name} (${item.exchange})`;

    button.appendChild(symbolSpan);
    button.appendChild(nameSpan);

    button.addEventListener("click", () => {
      symbolInput.value = item.symbol;
      hideSuggestions();
      form.requestSubmit();
    });

    listItem.appendChild(button);
    suggestionsNode.appendChild(listItem);
  }

  suggestionsNode.hidden = false;
}

async function loadSuggestions() {
  const query = symbolInput.value.trim();

  if (!query) {
    hideSuggestions();
    return;
  }

  const currentRequestId = ++suggestionRequestId;

  try {
    const response = await fetch(`/api/tickers?query=${encodeURIComponent(query)}&limit=12`);
    const data = await response.json();

    if (currentRequestId !== suggestionRequestId) {
      return;
    }

    if (!response.ok) {
      hideSuggestions();
      return;
    }

    renderSuggestions(data.tickers || []);
  } catch (error) {
    if (currentRequestId === suggestionRequestId) {
      hideSuggestions();
    }
  }
}

function queueSuggestionsLoad() {
  clearTimeout(suggestionTimer);
  suggestionTimer = setTimeout(loadSuggestions, 140);
}

function renderTopStocks(items) {
  topStocksNode.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    topStocksNode.textContent = "Geen top tickers beschikbaar.";
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

    topStocksNode.appendChild(button);
  }
}

async function loadTopStocks() {
  topStocksNode.textContent = "Top 10 laden...";

  try {
    const response = await fetch("/api/top-stocks?limit=10");
    const data = await response.json();

    if (!response.ok) {
      topStocksNode.textContent = "Top 10 kon niet worden geladen.";
      return;
    }

    renderTopStocks(data.items || []);
  } catch (error) {
    topStocksNode.textContent = "Top 10 kon niet worden geladen.";
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
  const ctx = document.getElementById("stock-chart").getContext("2d");
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

  if (chart) {
    chart.destroy();
  }
  chart = new Chart(ctx, config);
}

function updateStats(data) {
  statsCard.hidden = false;
  lastCloseNode.textContent = `$${data.stats.last_close.toFixed(2)}`;

  const sign = data.stats.daily_trend_pct >= 0 ? "+" : "";
  trendNode.textContent = `${sign}${data.stats.daily_trend_pct.toFixed(3)}% / dag`;

  if (data.engine_used === "ai") {
    modelNameNode.textContent = "AI model";
  } else if (data.engine_used === "stat_fallback") {
    modelNameNode.textContent = "Statistisch (AI fallback)";
  } else {
    modelNameNode.textContent = "Statistisch model";
  }

  disclaimerNode.textContent = `${data.disclaimer} ${data.engine_note || ""}`.trim();
}

async function loadPrediction(event) {
  event.preventDefault();

  const symbol = symbolInput.value.trim().toUpperCase();
  const horizon = Number.parseInt(horizonInput.value, 10);
  if (!symbol) {
    setStatus("Vul een ticker symbool in.", true);
    return;
  }

  symbolInput.value = symbol;
  hideSuggestions();
  setStatus("Data laden en voorspelling berekenen...");

  try {
    const response = await fetch(
      `/api/predict?symbol=${encodeURIComponent(symbol)}&horizon=${horizon}&engine=stat`,
    );
    const data = await response.json();

    if (!response.ok) {
      setStatus(data.detail || "Fout bij ophalen van data.", true);
      return;
    }

    renderChart(data);
    updateStats(data);

    const requested = data.requested_symbol || symbol;
    const symbolLabel = requested !== data.symbol ? `${requested} -> ${data.symbol}` : data.symbol;

    setStatus(`Voorspelling geladen voor ${symbolLabel} (${data.engine_used}).`);
  } catch (error) {
    setStatus("Netwerkfout: kan de API niet bereiken.", true);
  }
}

form.addEventListener("submit", loadPrediction);
symbolInput.addEventListener("input", queueSuggestionsLoad);
symbolInput.addEventListener("focus", queueSuggestionsLoad);
symbolInput.addEventListener("keydown", (event) => {
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

loadTopStocks();
form.requestSubmit();