// Number and date formatting shared by the screens; mirrors the helpers in frontend/app.js.

const CURRENCY_LOCALES: Record<string, string> = {
  USD: "en-US",
  EUR: "de-DE",
  GBP: "en-GB",
  JPY: "ja-JP",
  CHF: "de-CH",
  CAD: "en-CA",
  AUD: "en-AU",
};

function localeFor(code: string) {
  return CURRENCY_LOCALES[code] ?? "en-US";
}

// Sub-cent prices (small crypto) keep four significant digits instead of reading as 0.00.
function isSubCent(value: number) {
  return value !== 0 && Math.abs(value) < 0.01;
}

export function formatPrice(value: number, currency: string) {
  const code = currency || "USD";
  try {
    return new Intl.NumberFormat(localeFor(code), {
      style: "currency",
      currency: code,
      ...(isSubCent(value)
        ? { maximumSignificantDigits: 4 }
        : { maximumFractionDigits: code === "JPY" ? 0 : 2 }),
    }).format(value);
  } catch {
    return `${Number.isFinite(value) ? value.toFixed(2) : "0.00"} ${code}`;
  }
}

export function formatAxisPrice(value: number, currency: string) {
  const code = currency || "USD";
  const abs = Math.abs(value);
  try {
    return new Intl.NumberFormat(localeFor(code), {
      style: "currency",
      currency: code,
      notation: abs >= 10000 ? "compact" : "standard",
      ...(isSubCent(value)
        ? { maximumSignificantDigits: 3 }
        : { minimumFractionDigits: 0, maximumFractionDigits: abs >= 100 ? 0 : 2 }),
    }).format(value);
  } catch {
    return String(Math.round(value));
  }
}

export function formatPercent(value: number) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export type Tone = "up" | "down" | "flat";

// Direction is always spelled out with a glyph as well as a color.
export function formatDelta(pct: number): { text: string; tone: Tone } {
  if (pct > 0) return { text: `▲ ${formatPercent(pct)}`, tone: "up" };
  if (pct < 0) return { text: `▼ ${formatPercent(pct)}`, tone: "down" };
  return { text: `▬ ${formatPercent(pct)}`, tone: "flat" };
}

export function formatDays(days: number) {
  return `${days} ${days === 1 ? "day" : "days"}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ISO dates are formatted by hand: Intl date support differs between Hermes builds.
export function formatDate(iso: string, withYear = false) {
  const [year, month, day] = String(iso).slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return String(iso);
  const short = `${MONTHS[month - 1]} ${day}`;
  return withYear ? `${short}, ${year}` : short;
}

// Error reasons come from the network layer ("Failed to fetch"); end them like a sentence.
export function asSentence(text: string) {
  const value = String(text || "").trim();
  return !value || /[.!?]$/.test(value) ? value : `${value}.`;
}

export function sentenceCase(text: string) {
  const value = String(text || "");
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

const FEATURE_ACRONYMS = new Set(["sma", "ema", "rsi", "macd", "bb"]);

export function formatFeatureName(raw: string) {
  const text = String(raw || "")
    .split("_")
    .map((word) => (FEATURE_ACRONYMS.has(word.toLowerCase()) ? word.toUpperCase() : word))
    .join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const SOURCE_LABELS: Record<string, string> = {
  ml_analog: "ML analog",
  stat: "Statistical baseline",
  stat_fallback: "Statistical fallback",
  ml_pattern_difference: "Pattern-difference analysis",
  unknown: "Unknown",
};

export function formatSourceLabel(value: string | null | undefined) {
  return SOURCE_LABELS[value ?? "unknown"] ?? String(value || "Unknown").replace(/_/g, " ");
}
