import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { ForecastEngine, PredictResponse, SupportedCurrency } from "@/api/types";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { ForecastChart } from "@/components/ForecastChart";
import { ForecastTable } from "@/components/ForecastTable";
import { Note } from "@/components/Note";
import { TextToggle } from "@/components/TextToggle";
import { getDemoForecast } from "@/data/demoAssets";
import { useWatchlist } from "@/context/WatchlistContext";
import type { RootStackParamList } from "@/navigation/types";
import { defaultEngineFor, loadForecast } from "@/services/marketService";
import { createAsyncStorageAdapter } from "@/storage/storage";
import { makeStyles, useTheme } from "@/theme/theme";
import {
  asSentence,
  formatDate,
  formatDays,
  formatDelta,
  formatFeatureName,
  formatPrice,
  formatSourceLabel,
  sentenceCase,
} from "@/utils/format";

type Props = NativeStackScreenProps<RootStackParamList, "AssetDetail">;

const CURRENCY_STORAGE_KEY = "aurion-currency";
const CURRENCIES: SupportedCurrency[] = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"];
const ENGINES: ForecastEngine[] = ["ml", "stat"];
const ENGINE_LABELS: Record<ForecastEngine, string> = { ml: "ML analog", stat: "Statistical" };
const HORIZONS = ["7", "14", "21", "30", "45"] as const;
type Horizon = (typeof HORIZONS)[number];
const HORIZON_LABELS: Record<Horizon, string> = { "7": "7d", "14": "14d", "21": "21d", "30": "30d", "45": "45d" };
const storage = createAsyncStorageAdapter();

/* ── Small building blocks ──────────────────────────────────────────── */

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  const styles = useStyles();
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <View style={styles.factValue}>{children}</View>
    </View>
  );
}

function Backtest({ evaluation }: { evaluation: PredictResponse["evaluation"] }) {
  const styles = useStyles();
  if (!evaluation) return null;

  const rows: [string, string][] = [
    [
      "Direction called correctly",
      evaluation.directional_accuracy != null ? `${(evaluation.directional_accuracy * 100).toFixed(0)}%` : "-",
    ],
    ["Mean absolute error", evaluation.mae != null ? evaluation.mae.toFixed(2) : "-"],
    // Two decimals: the forecast and the no-change guess often differ by less than 0.1 point.
    ["Mean absolute % error", evaluation.mape != null ? `${evaluation.mape.toFixed(2)}%` : "-"],
    [
      "% error of a no-change guess",
      evaluation.no_change_mape != null ? `${evaluation.no_change_mape.toFixed(2)}%` : "-",
    ],
    [
      "Beats a no-change guess",
      evaluation.beats_no_change === true ? "Yes" : evaluation.beats_no_change === false ? "No" : "-",
    ],
    ["Validation windows", evaluation.validation_windows != null ? String(evaluation.validation_windows) : "-"],
  ];

  return (
    <View style={styles.section}>
      <Text style={styles.sectionLabel} accessibilityRole="header">
        How this forecast did on recent history
      </Text>
      {rows.map(([label, value]) => (
        <View key={label} style={styles.listRow}>
          <Text style={styles.listLabel}>{label}</Text>
          <Text style={styles.listValue}>{value}</Text>
        </View>
      ))}
      {evaluation.beats_no_change === false ? (
        <View style={styles.backtestNote}>
          <Note>
            On recent history this forecast missed by more than simply assuming the price stays where it
            is. Read its direction as a guess and lean on the range.
          </Note>
        </View>
      ) : null}
    </View>
  );
}

function Explanation({ data }: { data: PredictResponse }) {
  const styles = useStyles();
  const explanation = data.explanation;
  if (!explanation || explanation.top_features.length === 0) return null;

  const maxScore = Math.max(...explanation.top_features.map((feature) => feature.difference_score), 0.01);
  // The explanation can outlive a rejected ML forecast; say so only when the fallback is what you see.
  const fromFallback = data.source.forecast === "stat_fallback" && Boolean(data.source.analysis);

  return (
    <View style={styles.section}>
      <Text style={styles.sectionLabel} accessibilityRole="header">
        How today's pattern differs from its closest analogs
      </Text>
      <Text style={styles.fine}>
        Forecast source: {formatSourceLabel(data.source.forecast)}. Explanation source:{" "}
        {formatSourceLabel(data.source.analysis)}.
      </Text>
      {fromFallback ? (
        <Note>
          Final forecast uses the statistical fallback. This explanation summarizes how the current market
          pattern differed from the ML analog set before the quality gate rejected the forecast.
        </Note>
      ) : null}
      {explanation.narrative ? <Text style={styles.narrative}>{explanation.narrative}</Text> : null}

      <View style={styles.diverging}>
        <View style={styles.nameSpacer} />
        <Text style={[styles.divergingLabel, styles.alignRight]}>Lower</Text>
        <Text style={styles.divergingLabel}>Higher</Text>
        <View style={styles.dirSpacer} />
      </View>
      {explanation.top_features.map((feature) => {
        const width = `${Math.max(Math.round((feature.difference_score / maxScore) * 100), 2)}%` as const;
        return (
          <View
            key={feature.feature}
            style={styles.featureRow}
            accessible
            accessibilityLabel={`${formatFeatureName(feature.feature)}: ${feature.relation} than its analogs`}
          >
            <Text style={styles.featureName} numberOfLines={1}>
              {formatFeatureName(feature.feature)}
            </Text>
            <View style={styles.half}>
              {feature.relation === "lower" ? <View style={[styles.bar, styles.barLower, { width }]} /> : null}
            </View>
            <View style={styles.axis} />
            <View style={styles.half}>
              {feature.relation === "higher" ? <View style={[styles.bar, styles.barHigher, { width }]} /> : null}
              {feature.relation === "similar" ? <View style={styles.similar} /> : null}
            </View>
            <Text style={styles.featureDir}>{feature.relation}</Text>
          </View>
        );
      })}
      {explanation.nearest_analog_date ? (
        <Text style={styles.fine}>Nearest analog: {formatDate(explanation.nearest_analog_date, true)}</Text>
      ) : null}
    </View>
  );
}

/* ── Main screen ────────────────────────────────────────────────────── */

export function AssetDetailScreen({ route, navigation }: Props) {
  const { symbol, assetType, name, engine: initialEngine } = route.params;
  const theme = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const { isSaved, toggle } = useWatchlist();
  const [data, setData] = useState<PredictResponse | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [demoReason, setDemoReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [currency, setCurrency] = useState<SupportedCurrency>("USD");
  const [engine, setEngine] = useState<ForecastEngine>(initialEngine ?? defaultEngineFor(assetType));
  const [horizon, setHorizon] = useState<Horizon>("7");

  // Load persisted currency preference on mount
  useEffect(() => {
    storage.getItem(CURRENCY_STORAGE_KEY).then((stored) => {
      if (stored && CURRENCIES.includes(stored as SupportedCurrency)) {
        setCurrency(stored as SupportedCurrency);
      }
    });
  }, []);

  // Persist currency whenever it changes
  const handleCurrencyChange = useCallback((value: SupportedCurrency) => {
    setCurrency(value);
    void storage.setItem(CURRENCY_STORAGE_KEY, value);
  }, []);

  // Fetch forecast whenever inputs change; the previous result stays on screen, dimmed, until the new one lands.
  useEffect(() => {
    let mounted = true;
    setLoading(true);

    loadForecast(symbol, assetType, {
      horizon: Number(horizon),
      engine,
      displayCurrency: currency,
    })
      .then((result) => {
        if (mounted) {
          setData(result.data);
          setIsDemo(result.isDemo);
          setDemoReason(result.reason ?? null);
        }
      })
      .catch(() => {
        if (mounted) {
          setData(getDemoForecast(symbol, assetType, currency, engine));
          setIsDemo(true);
          setDemoReason("The live forecast endpoint is unavailable.");
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
  const displayCurrency = data ? data.display_currency || data.currency : currency;
  const delta = data ? formatDelta(data.summary.expected_return_pct) : null;
  const subtitle = [name || data?.requested_symbol, data?.model_name, assetType === "crypto" ? "Crypto" : "Stock"]
    .filter(Boolean)
    .join(" · ");

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 48 }]}
    >
      <View style={styles.topRow}>
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="Back"
          hitSlop={8}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
        >
          <Text style={styles.backText}>{"←"} Back</Text>
        </Pressable>
        <Pressable
          onPress={() => toggle({ symbol, name: name || symbol, assetType })}
          accessibilityRole="button"
          style={({ pressed }) => [styles.quietButton, pressed && styles.pressed]}
        >
          <Text style={styles.quietText}>{saved ? "Remove from watchlist" : "Add to watchlist"}</Text>
        </Pressable>
      </View>

      <View style={styles.head}>
        <Text style={styles.symbol} accessibilityRole="header">
          {data?.symbol ?? symbol}
        </Text>
        <Text style={styles.model}>{subtitle}</Text>
      </View>

      <View style={styles.controls}>
        <View style={styles.controlRow}>
          <Text style={styles.controlLabel}>Horizon</Text>
          <TextToggle
            options={HORIZONS}
            value={horizon}
            labels={HORIZON_LABELS}
            onChange={setHorizon}
            accessibilityLabel="Forecast horizon"
          />
        </View>
        <View style={styles.controlRow}>
          <Text style={styles.controlLabel}>Model</Text>
          <TextToggle
            options={ENGINES}
            value={engine}
            labels={ENGINE_LABELS}
            onChange={setEngine}
            accessibilityLabel="Forecast model"
          />
        </View>
        <View style={styles.controlRow}>
          <Text style={styles.controlLabel}>Currency</Text>
          <View style={styles.controlValue}>
            <TextToggle
              options={CURRENCIES}
              value={currency}
              onChange={handleCurrencyChange}
              accessibilityLabel="Display currency"
              size="small"
            />
          </View>
        </View>
      </View>

      {!data ? (
        <View style={styles.loading} accessibilityLiveRegion="polite">
          <ActivityIndicator size="small" color={theme.colors.ink3} />
          <Text style={styles.loadingText}>Running the forecast for {symbol}...</Text>
        </View>
      ) : (
        <View style={[styles.result, loading && styles.refreshing]}>
          <Text style={styles.status} accessibilityLiveRegion="polite">
            {loading ? "Updating..." : " "}
          </Text>

          {isDemo ? (
            <Note tone="warning" lead="Demo data.">
              {asSentence(demoReason || "The live API is unavailable")} The numbers below are illustrative.
            </Note>
          ) : null}
          {/* Demo data is flagged as degraded too; the demo note above already says so. */}
          {data.degraded && !isDemo ? (
            <Note tone="warning" lead="Statistical fallback in use.">
              {data.degradation_message ||
                "The ML model did not pass its quality gate, so this is the statistical baseline."}
            </Note>
          ) : null}

          <View style={styles.hero}>
            <Text style={styles.heroLabel}>Expected price in {formatDays(data.horizon_days)}</Text>
            <Text style={styles.heroValue} adjustsFontSizeToFit numberOfLines={1}>
              {formatPrice(data.summary.expected_price, displayCurrency)}
            </Text>
            <View style={styles.heroDelta}>
              {delta ? (
                <Text style={[styles.delta, delta.tone === "up" && styles.up, delta.tone === "down" && styles.down]}>
                  {delta.text}
                </Text>
              ) : null}
              <Text style={styles.heroFrom}>
                from the last close of {formatPrice(data.stats.last_close, displayCurrency)}{" "}
                <Text style={styles.currencyTag}>{displayCurrency}</Text>
              </Text>
            </View>
          </View>

          <View style={styles.facts}>
            <Fact label="Outlook">
              <Text style={styles.factText}>{sentenceCase(data.summary.signal)}</Text>
            </Fact>
            <Fact label="Trend">
              <Text style={styles.factText}>{sentenceCase(data.summary.trend)}</Text>
            </Fact>
            <Fact label="Confidence">
              <ConfidenceMeter tier={data.summary.confidence_tier} />
            </Fact>
            <Fact label="Data and model">
              <Text style={styles.factMono}>
                {data.source.market_data} / {data.source.forecast}
              </Text>
            </Fact>
          </View>

          {data.source.data_warnings.map((warning) => (
            <Note key={warning} tone="warning">
              {warning}
            </Note>
          ))}

          <View style={styles.chart}>
            <ForecastChart
              history={data.history}
              forecast={data.forecast}
              currency={displayCurrency}
              horizonDays={data.horizon_days}
            />
            <ForecastTable forecast={data.forecast} currency={displayCurrency} />
          </View>

          <Backtest evaluation={data.evaluation} />
          <Explanation data={data} />

          <Text style={[styles.fine, styles.disclaimer]}>
            {`${data.disclaimer || ""} ${data.engine_note || ""}`.trim()}
          </Text>
        </View>
      )}
    </ScrollView>
  );
}

/* ── Styles ─────────────────────────────────────────────────────────── */

const useStyles = makeStyles((theme) => ({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.surface,
  },
  content: {
    paddingHorizontal: theme.gutter,
  },
  pressed: {
    opacity: 0.6,
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    minHeight: 44,
  },
  back: {
    paddingVertical: theme.space.sm,
  },
  backText: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  quietButton: {
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: theme.space.md,
    borderWidth: 1,
    borderColor: theme.colors.rule,
    borderRadius: theme.radius,
  },
  quietText: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  head: {
    paddingTop: theme.space.lg,
    paddingBottom: theme.space.lg,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  symbol: {
    fontSize: 28,
    lineHeight: 34,
    letterSpacing: -0.3,
    fontFamily: theme.fonts.monoMedium,
    color: theme.colors.ink,
  },
  model: {
    ...theme.text.small,
    marginTop: 2,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  controls: {
    paddingVertical: theme.space.md,
    gap: theme.space.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  controlRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.space.lg,
  },
  controlLabel: {
    ...theme.text.fine,
    width: 64,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink3,
  },
  controlValue: {
    flex: 1,
  },
  loading: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.space.sm,
    paddingVertical: theme.space.xxl,
  },
  loadingText: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  result: {
    gap: theme.space.md,
  },
  refreshing: {
    opacity: 0.45,
  },
  status: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    marginTop: theme.space.sm,
  },
  hero: {
    marginTop: theme.space.sm,
  },
  heroLabel: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  heroValue: {
    fontSize: 46,
    lineHeight: 54,
    letterSpacing: -1.2,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
    marginTop: 2,
    marginBottom: 6,
  },
  heroDelta: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "baseline",
    columnGap: 10,
    rowGap: 2,
  },
  delta: {
    ...theme.text.lead,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink2,
  },
  up: {
    color: theme.colors.up,
  },
  down: {
    color: theme.colors.down,
  },
  heroFrom: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  currencyTag: {
    ...theme.text.fine,
    fontFamily: theme.fonts.mono,
    color: theme.colors.ink3,
  },
  facts: {
    marginTop: theme.space.lg,
    borderTopWidth: 1,
    borderTopColor: theme.colors.ink,
  },
  fact: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: theme.space.lg,
    minHeight: 44,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  factLabel: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  factValue: {
    flexShrink: 1,
    alignItems: "flex-end",
  },
  factText: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink,
    textAlign: "right",
  },
  factMono: {
    ...theme.text.small,
    fontFamily: theme.fonts.mono,
    color: theme.colors.ink,
    textAlign: "right",
  },
  chart: {
    marginTop: theme.space.xxl,
    gap: theme.space.sm,
  },
  section: {
    marginTop: theme.space.xl,
    paddingTop: theme.space.xl,
    borderTopWidth: 1,
    borderTopColor: theme.colors.grid,
    gap: theme.space.sm,
  },
  sectionLabel: {
    ...theme.text.small,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
    marginBottom: theme.space.xs,
  },
  listRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: theme.space.lg,
    paddingVertical: theme.space.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  listLabel: {
    ...theme.text.small,
    flexShrink: 1,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  listValue: {
    ...theme.text.small,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink,
    fontVariant: ["tabular-nums"],
  },
  backtestNote: {
    marginTop: theme.space.sm,
  },
  narrative: {
    ...theme.text.body,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  diverging: {
    flexDirection: "row",
    marginTop: theme.space.sm,
  },
  divergingLabel: {
    ...theme.text.fine,
    flex: 1,
    fontSize: 12,
    paddingHorizontal: theme.space.sm,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  alignRight: {
    textAlign: "right",
  },
  nameSpacer: {
    width: 104,
  },
  dirSpacer: {
    width: 56,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: 28,
  },
  featureName: {
    ...theme.text.fine,
    width: 104,
    paddingRight: theme.space.sm,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  half: {
    flex: 1,
    height: 10,
    flexDirection: "row",
  },
  axis: {
    width: 1,
    alignSelf: "stretch",
    backgroundColor: theme.colors.rule,
  },
  bar: {
    height: 10,
    backgroundColor: theme.colors.ink2,
  },
  barLower: {
    marginLeft: "auto",
    borderTopLeftRadius: 4,
    borderBottomLeftRadius: 4,
  },
  barHigher: {
    borderTopRightRadius: 4,
    borderBottomRightRadius: 4,
  },
  similar: {
    width: 3,
    height: 10,
    borderRadius: 2,
    backgroundColor: theme.colors.ink2,
  },
  featureDir: {
    ...theme.text.fine,
    width: 56,
    paddingLeft: theme.space.sm,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  fine: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  disclaimer: {
    marginTop: theme.space.xxl,
  },
}));
