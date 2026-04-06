import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";

import type { ForecastEngine, PredictResponse, SupportedCurrency } from "@/api/types";
import { getDemoForecast } from "@/data/demoAssets";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { ForecastCard } from "@/components/ForecastCard";
import { TrendChip } from "@/components/TrendChip";
import { useWatchlist } from "@/context/WatchlistContext";
import { theme } from "@/theme/theme";
import type { RootStackParamList } from "@/navigation/types";
import { loadForecast } from "@/services/marketService";

type Props = NativeStackScreenProps<RootStackParamList, "AssetDetail">;

const CURRENCY_STORAGE_KEY = "aurion-currency";
const CURRENCIES: SupportedCurrency[] = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"];
const ENGINES: ForecastEngine[] = ["ml", "stat", "ai"];
const ENGINE_LABELS: Record<ForecastEngine, string> = { ml: "ML", stat: "Stat", ai: "AI" };
const MIN_HORIZON = 7;
const MAX_HORIZON = 45;

function ChartPlaceholder({ points }: { points: PredictResponse["history"] }) {
  const recent = points.slice(-10);
  return (
    <View style={styles.chart}>
      <View style={styles.chartGrid}>
        {Array.from({ length: 5 }).map((_, index) => (
          <View key={index} style={styles.chartGridLine} />
        ))}
      </View>
      <View style={styles.chartBars}>
        {recent.map((point, index) => (
          <View
            key={point.date}
            style={[
              styles.bar,
              {
                height: 36 + ((point.close % 11) * 4),
                opacity: 0.35 + index * 0.06,
              },
            ]}
          />
        ))}
      </View>
      <Text style={styles.chartCaption}>Chart placeholder. Replace with a real library later.</Text>
    </View>
  );
}

function formatSignalLabel(signal: PredictResponse["summary"]["signal"]) {
  return signal
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/* ── Picker row (currency / engine) ─────────────────────────────────── */

function PillPicker<T extends string>({
  label,
  options,
  value,
  labelMap,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: T;
  labelMap?: Record<T, string>;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.pickerRow}>
      <Text style={styles.pickerLabel}>{label}</Text>
      <View style={styles.pillGroup}>
        {options.map((opt) => (
          <Pressable
            key={opt}
            onPress={() => onChange(opt)}
            style={[styles.pill, opt === value && styles.pillActive]}
          >
            <Text style={[styles.pillText, opt === value && styles.pillTextActive]}>
              {labelMap ? labelMap[opt] : opt}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

/* ── Horizon slider (pure RN, no external lib) ──────────────────────── */

function HorizonSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const step = 1;
  const range = MAX_HORIZON - MIN_HORIZON;
  const pct = ((value - MIN_HORIZON) / range) * 100;

  const decrement = () => onChange(Math.max(MIN_HORIZON, value - step));
  const increment = () => onChange(Math.min(MAX_HORIZON, value + step));

  return (
    <View style={styles.sliderCard}>
      <View style={styles.sliderHeader}>
        <Text style={styles.pickerLabel}>Horizon</Text>
        <Text style={styles.sliderValue}>{value} days</Text>
      </View>
      <View style={styles.sliderTrackContainer}>
        <Pressable onPress={decrement} style={styles.sliderButton}>
          <Text style={styles.sliderButtonText}>-</Text>
        </Pressable>
        <View style={styles.sliderTrack}>
          <View style={[styles.sliderFill, { width: `${pct}%` }]} />
        </View>
        <Pressable onPress={increment} style={styles.sliderButton}>
          <Text style={styles.sliderButtonText}>+</Text>
        </Pressable>
      </View>
      <View style={styles.sliderLabels}>
        <Text style={styles.sliderLabelText}>{MIN_HORIZON}d</Text>
        <Text style={styles.sliderLabelText}>{MAX_HORIZON}d</Text>
      </View>
    </View>
  );
}

/* ── Explanation card ───────────────────────────────────────────────── */

function ExplanationCard({ explanation }: { explanation: PredictResponse["explanation"] }) {
  if (!explanation) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Explanation</Text>
      <Text style={styles.note}>{explanation.narrative}</Text>

      {explanation.top_features.length > 0 && (
        <View style={styles.featureList}>
          <Text style={styles.featureHeading}>Top features</Text>
          {explanation.top_features.map((feat) => (
            <View key={feat.feature} style={styles.featureRow}>
              <Text style={styles.featureName}>{feat.feature}</Text>
              <View
                style={[
                  styles.relationBadge,
                  feat.relation === "higher"
                    ? styles.relationHigher
                    : feat.relation === "lower"
                      ? styles.relationLower
                      : styles.relationSimilar,
                ]}
              >
                <Text style={styles.relationText}>{feat.relation}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {explanation.nearest_analog_date ? (
        <Text style={styles.note}>
          Nearest analog: {explanation.nearest_analog_date}
        </Text>
      ) : null}
    </View>
  );
}

/* ── Evaluation metrics row ─────────────────────────────────────────── */

function EvaluationMetrics({ evaluation }: { evaluation: PredictResponse["evaluation"] }) {
  if (!evaluation) return null;

  const metrics: { label: string; value: string | null }[] = [
    { label: "MAE", value: evaluation.mae != null ? evaluation.mae.toFixed(2) : null },
    { label: "MAPE", value: evaluation.mape != null ? `${evaluation.mape.toFixed(1)}%` : null },
    {
      label: "Dir. Acc.",
      value: evaluation.directional_accuracy != null ? `${(evaluation.directional_accuracy * 100).toFixed(0)}%` : null,
    },
  ];

  const visible = metrics.filter((m) => m.value !== null);
  if (visible.length === 0) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Evaluation</Text>
      <View style={styles.metricsRow}>
        {visible.map((m) => (
          <View key={m.label} style={styles.metricBadge}>
            <Text style={styles.metricValue}>{m.value}</Text>
            <Text style={styles.metricLabel}>{m.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ── Main screen ────────────────────────────────────────────────────── */

export function AssetDetailScreen({ route, navigation }: Props) {
  const { symbol, assetType, name, engine: initialEngine } = route.params;
  const { isSaved, toggle } = useWatchlist();
  const [data, setData] = useState<PredictResponse>(() => getDemoForecast(symbol, assetType));
  const [loading, setLoading] = useState(true);

  const [currency, setCurrency] = useState<SupportedCurrency>("USD");
  const [engine, setEngine] = useState<ForecastEngine>(initialEngine ?? "ml");
  const [horizon, setHorizon] = useState(7);

  // Load persisted currency preference on mount
  useEffect(() => {
    AsyncStorage.getItem(CURRENCY_STORAGE_KEY).then((stored) => {
      if (stored && CURRENCIES.includes(stored as SupportedCurrency)) {
        setCurrency(stored as SupportedCurrency);
      }
    });
  }, []);

  // Persist currency whenever it changes
  const handleCurrencyChange = useCallback((value: SupportedCurrency) => {
    setCurrency(value);
    AsyncStorage.setItem(CURRENCY_STORAGE_KEY, value);
  }, []);

  // Fetch forecast whenever inputs change
  useEffect(() => {
    let mounted = true;
    setLoading(true);

    loadForecast(symbol, assetType, {
      horizon,
      engine,
      displayCurrency: currency,
    })
      .then((payload) => {
        if (mounted) {
          setData(payload);
        }
      })
      .catch(() => {
        if (mounted) {
          setData(getDemoForecast(symbol, assetType));
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [assetType, symbol, horizon, engine, currency]);

  const saved = isSaved(symbol);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.topRow}>
        <Pressable onPress={() => navigation.goBack()} style={styles.backButton}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Pressable
          onPress={() => toggle({ symbol, name: name || symbol, assetType })}
          style={[styles.watchButton, saved && styles.watchButtonActive]}
        >
          <Text style={styles.watchButtonText}>{saved ? "Saved" : "Save"}</Text>
        </Pressable>
      </View>

      <View style={styles.hero}>
        <View style={{ flex: 1 }}>
          <Text style={styles.symbol}>{data.symbol}</Text>
          <Text style={styles.name}>{name || data.requested_symbol}</Text>
        </View>
        <TrendChip trend={data.summary.trend} />
      </View>

      {/* ── Controls card ──────────────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Settings</Text>
        <PillPicker
          label="Currency"
          options={CURRENCIES}
          value={currency}
          onChange={handleCurrencyChange}
        />
        <PillPicker
          label="Engine"
          options={ENGINES}
          value={engine}
          labelMap={ENGINE_LABELS}
          onChange={setEngine}
        />
        <HorizonSlider value={horizon} onChange={setHorizon} />
      </View>

      {/* ── Forecast summary ──────────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{loading ? "Loading forecast..." : "Forecast summary"}</Text>
        <Text style={styles.stat}>
          Last close {data.currency} {data.stats.last_close.toFixed(2)}
        </Text>
        <Text style={styles.stat}>
          Expected {data.currency} {data.summary.expected_price.toFixed(2)} ({data.summary.expected_return_pct.toFixed(2)}%)
        </Text>
        <Text style={styles.stat}>
          Outlook {formatSignalLabel(data.summary.signal)}
        </Text>
        <Text style={styles.note}>{data.engine_note}</Text>
        {data.evaluation?.validation_windows != null ? (
          <Text style={styles.note}>Validated on {data.evaluation.validation_windows} windows.</Text>
        ) : null}
      </View>

      <ChartPlaceholder points={data.history} />

      {/* ── Prediction bands ──────────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Prediction bands</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.forecastRow}>
          {data.forecast.map((point) => (
            <ForecastCard key={point.date} {...point} />
          ))}
        </ScrollView>
      </View>

      {/* ── Confidence ────────────────────────────────────────────── */}
      <View style={styles.card}>
        <ConfidenceMeter
          tier={data.summary.confidence_tier}
          degraded={data.degraded}
        />
      </View>

      {/* ── Explanation (if available) ────────────────────────────── */}
      <ExplanationCard explanation={data.explanation} />

      {/* ── Evaluation metrics (if available) ─────────────────────── */}
      <EvaluationMetrics evaluation={data.evaluation} />

      {/* ── Model output footer ───────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Model output</Text>
        <Text style={styles.note}>
          This MVP exposes trend direction, banded forecast and confidence. No guarantee, no advice.
        </Text>
        {data.degraded && data.degradation_message ? <Text style={styles.warning}>{data.degradation_message}</Text> : null}
        <Text style={styles.note}>
          Source {data.source.market_data} / {data.source.forecast}
        </Text>
        <Text style={styles.footerText}>{data.disclaimer}</Text>
      </View>
    </ScrollView>
  );
}

/* ── Styles ─────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.space.xl,
    gap: theme.space.lg,
    paddingBottom: 48,
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  backButton: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 999,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  backText: {
    color: theme.colors.textPrimary,
    fontWeight: "700",
  },
  watchButton: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 999,
    backgroundColor: theme.colors.accentSoft,
  },
  watchButtonActive: {
    backgroundColor: theme.colors.successSoft,
  },
  watchButtonText: {
    color: theme.colors.textPrimary,
    fontWeight: "800",
  },
  hero: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: theme.space.md,
  },
  symbol: {
    color: theme.colors.textPrimary,
    fontSize: 36,
    fontWeight: "900",
  },
  name: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.md,
    marginTop: 4,
  },
  card: {
    gap: theme.space.sm,
    padding: theme.space.md,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  cardTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
  },
  stat: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.md,
    fontWeight: "600",
  },
  note: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    lineHeight: 20,
  },
  warning: {
    color: theme.colors.warning,
    fontSize: theme.fontSizes.sm,
    lineHeight: 20,
    fontWeight: "600",
  },
  footerText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    lineHeight: 18,
  },
  chart: {
    minHeight: 220,
    borderRadius: theme.radius.xl,
    padding: theme.space.md,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    justifyContent: "space-between",
    overflow: "hidden",
  },
  chartGrid: {
    position: "absolute",
    left: theme.space.md,
    right: theme.space.md,
    top: theme.space.md,
    bottom: 44,
    justifyContent: "space-between",
  },
  chartGridLine: {
    height: 1,
    backgroundColor: theme.colors.border,
    opacity: 0.7,
  },
  chartBars: {
    flex: 1,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8,
    paddingTop: 16,
    paddingBottom: 32,
  },
  bar: {
    flex: 1,
    borderRadius: 999,
    backgroundColor: theme.colors.accent,
  },
  chartCaption: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
  },
  forecastRow: {
    gap: theme.space.md,
    paddingVertical: theme.space.sm,
  },

  /* ── Picker / pill styles ──────────────────────────────────────── */
  pickerRow: {
    gap: theme.space.xs,
  },
  pickerLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    fontWeight: "700",
  },
  pillGroup: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.space.xs,
  },
  pill: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  pillActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: theme.colors.accent,
  },
  pillText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
  },
  pillTextActive: {
    color: theme.colors.accent,
  },

  /* ── Horizon slider styles ─────────────────────────────────────── */
  sliderCard: {
    gap: theme.space.xs,
  },
  sliderHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  sliderValue: {
    color: theme.colors.accent,
    fontSize: theme.fontSizes.sm,
    fontWeight: "800",
  },
  sliderTrackContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.space.sm,
  },
  sliderButton: {
    width: 32,
    height: 32,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    justifyContent: "center",
    alignItems: "center",
  },
  sliderButtonText: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
    lineHeight: 20,
  },
  sliderTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.surfaceElevated,
    overflow: "hidden",
  },
  sliderFill: {
    height: 6,
    borderRadius: 3,
    backgroundColor: theme.colors.accent,
  },
  sliderLabels: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 42,
  },
  sliderLabelText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
  },

  /* ── Explanation card styles ───────────────────────────────────── */
  featureList: {
    gap: theme.space.xs,
    marginTop: theme.space.xs,
  },
  featureHeading: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.sm,
    fontWeight: "700",
  },
  featureRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 4,
  },
  featureName: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.sm,
    flex: 1,
  },
  relationBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
  },
  relationHigher: {
    backgroundColor: theme.colors.successSoft,
  },
  relationLower: {
    backgroundColor: theme.colors.dangerSoft,
  },
  relationSimilar: {
    backgroundColor: theme.colors.surfaceElevated,
  },
  relationText: {
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
    color: theme.colors.textPrimary,
  },

  /* ── Evaluation metrics styles ─────────────────────────────────── */
  metricsRow: {
    flexDirection: "row",
    gap: theme.space.sm,
    flexWrap: "wrap",
  },
  metricBadge: {
    flex: 1,
    minWidth: 80,
    alignItems: "center",
    paddingVertical: theme.space.sm,
    paddingHorizontal: theme.space.sm,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  metricValue: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.md,
    fontWeight: "800",
  },
  metricLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    fontWeight: "600",
    marginTop: 2,
  },
});
