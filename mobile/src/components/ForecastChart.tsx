import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import type { ForecastPoint, HistoryPoint } from "@/api/types";
import { theme } from "@/theme/theme";

type ChartPoint =
  | { key: string; x: number; y: number; value: number; kind: "history" }
  | {
      key: string;
      x: number;
      y: number;
      value: number;
      lowerY: number;
      upperY: number;
      kind: "forecast";
    };

type HistoryChartPoint = Extract<ChartPoint, { kind: "history" }>;
type ForecastChartPoint = Extract<ChartPoint, { kind: "forecast" }>;

const CHART_HEIGHT = 176;
const MIN_WIDTH = 320;
const STEP_WIDTH = 18;
const PLOT_PADDING_X = 12;
const PLOT_PADDING_Y = 12;

function formatCompact(value: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      notation: "compact",
      maximumFractionDigits: value >= 1000 ? 1 : 2,
    }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function lineStyle(
  start: { x: number; y: number },
  end: { x: number; y: number },
  color: string,
  thickness = 2,
) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx);

  return {
    position: "absolute" as const,
    left: (start.x + end.x) / 2 - length / 2,
    top: (start.y + end.y) / 2 - thickness / 2,
    width: length,
    height: thickness,
    borderRadius: thickness,
    backgroundColor: color,
    transform: [{ rotateZ: `${angle}rad` }],
  };
}

export function ForecastChart({
  history,
  forecast,
  currency,
}: {
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  currency: string;
}) {
  const historySlice = history.slice(-20);
  const values = [
    ...historySlice.map((point) => point.close),
    ...forecast.flatMap((point) => [point.lower, point.predicted, point.upper]),
  ];
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const spread = Math.max(maxValue - minValue, Math.max(Math.abs(maxValue) * 0.08, 1));
  const domainMin = minValue - spread * 0.08;
  const domainMax = maxValue + spread * 0.08;
  const totalPoints = historySlice.length + forecast.length;
  const plotWidth = Math.max(MIN_WIDTH, totalPoints > 1 ? (totalPoints - 1) * STEP_WIDTH : MIN_WIDTH);
  const plotHeight = CHART_HEIGHT - PLOT_PADDING_Y * 2;
  const yForValue = (value: number) =>
    PLOT_PADDING_Y + (1 - (value - domainMin) / Math.max(domainMax - domainMin, 1)) * plotHeight;
  const xForIndex = (index: number) =>
    PLOT_PADDING_X + (totalPoints <= 1 ? plotWidth / 2 : index * STEP_WIDTH);

  const historyPoints: HistoryChartPoint[] = historySlice.map((point, index) => ({
    key: `history-${point.date}`,
    x: xForIndex(index),
    y: yForValue(point.close),
    value: point.close,
    kind: "history",
  }));
  const forecastPoints: ForecastChartPoint[] = forecast.map((point, index) => ({
    key: `forecast-${point.date}`,
    x: xForIndex(historySlice.length + index),
    y: yForValue(point.predicted),
    lowerY: yForValue(point.lower),
    upperY: yForValue(point.upper),
    value: point.predicted,
    kind: "forecast",
  }));
  const allPoints = [...historyPoints, ...forecastPoints];
  const forecastStartX = forecastPoints[0]?.x ?? plotWidth;
  const plotAreaWidth = plotWidth + PLOT_PADDING_X * 2;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Price path</Text>
          <Text style={styles.subtitle}>Recent closes plus forecast range</Text>
        </View>
        <View style={styles.pricePill}>
          <Text style={styles.pricePillText}>{formatCompact(maxValue, currency)}</Text>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <View style={[styles.plot, { width: plotAreaWidth }]}>
          <View style={styles.grid}>
            {Array.from({ length: 4 }).map((_, index) => (
              <View key={`grid-${index}`} style={styles.gridLine} />
            ))}
          </View>
          {forecastPoints.length > 0 ? (
            <View
              style={[
                styles.forecastOverlay,
                {
                  left: forecastStartX - STEP_WIDTH / 2,
                  width: plotAreaWidth - forecastStartX,
                },
              ]}
            />
          ) : null}
          {forecastPoints.map((point) => (
            <View
              key={`band-${point.key}`}
              style={[
                styles.band,
                {
                  left: point.x - 4,
                  top: point.upperY,
                  height: Math.max(point.lowerY - point.upperY, 4),
                },
              ]}
            />
          ))}
          {allPoints.slice(1).map((point, index) => {
            const previous = allPoints[index];
            const isForecastLine = previous.kind === "forecast" || point.kind === "forecast";
            return (
              <View
                key={`line-${point.key}`}
                style={lineStyle(
                  previous,
                  point,
                  isForecastLine ? theme.colors.success : theme.colors.accent,
                  isForecastLine ? 3 : 2,
                )}
              />
            );
          })}
          {historyPoints.map((point) => (
            <View
              key={point.key}
              style={[
                styles.dot,
                styles.historyDot,
                {
                  left: point.x - 4,
                  top: point.y - 4,
                },
              ]}
            />
          ))}
          {forecastPoints.map((point) => (
            <View
              key={point.key}
              style={[
                styles.dot,
                styles.forecastDot,
                {
                  left: point.x - 5,
                  top: point.y - 5,
                },
              ]}
            />
          ))}
        </View>
      </ScrollView>

      <View style={styles.metaRow}>
        <View style={styles.legendRow}>
          <View style={[styles.legendSwatch, { backgroundColor: theme.colors.accent }]} />
          <Text style={styles.legendText}>History</Text>
          <View style={[styles.legendSwatch, { backgroundColor: theme.colors.success }]} />
          <Text style={styles.legendText}>Forecast</Text>
          <View style={[styles.legendSwatch, styles.bandLegend]} />
          <Text style={styles.legendText}>Range</Text>
        </View>
        <Text style={styles.metaText}>
          {formatCompact(minValue, currency)} - {formatCompact(maxValue, currency)}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: theme.space.sm,
    padding: theme.space.md,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: theme.space.sm,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    marginTop: 2,
  },
  pricePill: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  pricePillText: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
  },
  scrollContent: {
    paddingVertical: theme.space.xs,
  },
  plot: {
    height: CHART_HEIGHT,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.surfaceElevated,
    overflow: "hidden",
  },
  grid: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "space-between",
    paddingVertical: PLOT_PADDING_Y,
  },
  gridLine: {
    height: 1,
    backgroundColor: theme.colors.border,
  },
  forecastOverlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    backgroundColor: theme.colors.successSoft,
    opacity: 0.3,
  },
  band: {
    position: "absolute",
    width: 8,
    borderRadius: 999,
    backgroundColor: theme.colors.success,
    opacity: 0.18,
  },
  dot: {
    position: "absolute",
    width: 10,
    height: 10,
    borderRadius: 999,
    borderWidth: 2,
  },
  historyDot: {
    backgroundColor: theme.colors.surfaceElevated,
    borderColor: theme.colors.accent,
  },
  forecastDot: {
    backgroundColor: theme.colors.success,
    borderColor: theme.colors.background,
  },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: theme.space.md,
    flexWrap: "wrap",
  },
  legendRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flexWrap: "wrap",
  },
  legendSwatch: {
    width: 10,
    height: 10,
    borderRadius: 999,
  },
  bandLegend: {
    opacity: 0.25,
  },
  legendText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    fontWeight: "600",
  },
  metaText: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
  },
});
