import React, { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";

import type { PredictResponse } from "@/api/types";
import { getDemoForecast } from "@/data/demoAssets";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { ForecastCard } from "@/components/ForecastCard";
import { TrendChip } from "@/components/TrendChip";
import { useWatchlist } from "@/context/WatchlistContext";
import { theme } from "@/theme/theme";
import type { RootStackParamList } from "@/navigation/types";
import { loadForecast } from "@/services/marketService";

type Props = NativeStackScreenProps<RootStackParamList, "AssetDetail">;

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

export function AssetDetailScreen({ route, navigation }: Props) {
  const { symbol, assetType, name } = route.params;
  const { isSaved, toggle } = useWatchlist();
  const [data, setData] = useState<PredictResponse>(() => getDemoForecast(symbol, assetType));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    loadForecast(symbol, assetType)
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
  }, [assetType, symbol]);

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

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Prediction bands</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.forecastRow}>
          {data.forecast.map((point) => (
            <ForecastCard key={point.date} {...point} />
          ))}
        </ScrollView>
      </View>

      <View style={styles.card}>
        <ConfidenceMeter
          tier={data.summary.confidence_tier}
          degraded={data.degraded}
        />
      </View>

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
});
