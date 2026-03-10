const form = document.getElementById("predict-form");
const symbolInput = document.getElementById("symbol");
const horizonInput = document.getElementById("horizon");
const statusNode = document.getElementById("status");
const statsCard = document.getElementById("stats-card");
const lastCloseNode = document.getElementById("last-close");
const trendNode = document.getElementById("trend");
const disclaimerNode = document.getElementById("disclaimer");

let chart;

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.style.color = isError ? "#dc2626" : "#1d4ed8";
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

  disclaimerNode.textContent = data.disclaimer;
}

async function loadPrediction(event) {
  event.preventDefault();

  const symbol = symbolInput.value.trim().toUpperCase();
  const horizon = Number.parseInt(horizonInput.value, 10);

  if (!symbol) {
    setStatus("Vul een ticker symbool in.", true);
    return;
  }

  setStatus("Data laden en voorspelling berekenen...");

  try {
    const response = await fetch(`/api/predict?symbol=${encodeURIComponent(symbol)}&horizon=${horizon}`);
    const data = await response.json();

    if (!response.ok) {
      setStatus(data.detail || "Fout bij ophalen van data.", true);
      return;
    }

    renderChart(data);
    updateStats(data);
    setStatus(`Voorspelling geladen voor ${data.symbol}.`);
  } catch (error) {
    setStatus("Netwerkfout: kan de API niet bereiken.", true);
  }
}

form.addEventListener("submit", loadPrediction);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Non-blocking if registration fails.
    });
  });
}

form.requestSubmit();
