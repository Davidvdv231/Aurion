import React, { useMemo, useState } from "react";
import { type GestureResponderEvent, Text, View } from "react-native";
import Svg, { Circle, Line, Path, Text as SvgText } from "react-native-svg";

import type { ForecastPoint, HistoryPoint } from "@/api/types";
import { TextToggle } from "@/components/TextToggle";
import { fonts, makeStyles, useTheme } from "@/theme/theme";
import { formatAxisPrice, formatDate, formatPrice } from "@/utils/format";

const CHART_HEIGHT = 232;
const PAD_TOP = 10;
const PAD_BOTTOM = 24;
const PAD_RIGHT = 52;
const RANGES = ["1m", "3m", "6m"] as const;
type Range = (typeof RANGES)[number];
const RANGE_MONTHS: Record<Range, number> = { "1m": 1, "3m": 3, "6m": 6 };
const RANGE_LABELS: Record<Range, string> = { "1m": "1M", "3m": "3M", "6m": "6M" };

function sliceHistory(history: HistoryPoint[], range: Range) {
  if (history.length < 2) return history;
  const cutoff = new Date(`${history[history.length - 1].date.slice(0, 10)}T00:00:00Z`);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - RANGE_MONTHS[range]);
  const cutoffIso = cutoff.toISOString().slice(0, 10);
  const sliced = history.filter((row) => row.date >= cutoffIso);
  return sliced.length >= 2 ? sliced : history;
}

function niceTicks(min: number, max: number, count = 4) {
  const span = max - min;
  if (!(span > 0)) return [min];
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / magnitude;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let value = Math.ceil(min / step) * step; value <= max; value += step) {
    ticks.push(value);
  }
  return ticks;
}

function polyline(points: { x: number; y: number }[]) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
}

export function ForecastChart({
  history,
  forecast,
  currency,
  horizonDays,
}: {
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  currency: string;
  horizonDays: number;
}) {
  const theme = useTheme();
  const styles = useStyles();
  const { colors } = theme;
  const [range, setRange] = useState<Range>("3m");
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  const shown = useMemo(() => sliceHistory(history, range), [history, range]);

  const geometry = useMemo(() => {
    if (width <= 0 || shown.length === 0) return null;
    const values = [
      ...shown.map((point) => point.close),
      ...forecast.flatMap((point) => [point.lower, point.upper]),
    ];
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const pad = Math.max((rawMax - rawMin) * 0.06, Math.abs(rawMax) * 0.002, 0.01);
    const min = rawMin - pad;
    const max = rawMax + pad;
    const plotWidth = width - PAD_RIGHT;
    const plotHeight = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM;
    const total = shown.length + forecast.length;
    const x = (index: number) => (total <= 1 ? plotWidth / 2 : (index / (total - 1)) * plotWidth);
    const y = (value: number) => PAD_TOP + (1 - (value - min) / (max - min)) * plotHeight;
    const junction = shown.length - 1;
    const lastClose = shown[junction].close;

    const historyPath = polyline(shown.map((point, index) => ({ x: x(index), y: y(point.close) })));
    const anchor = { x: x(junction), y: y(lastClose) };
    const forecastPath = polyline([
      anchor,
      ...forecast.map((point, index) => ({ x: x(junction + 1 + index), y: y(point.predicted) })),
    ]);
    const upper = forecast.map((point, index) => ({ x: x(junction + 1 + index), y: y(point.upper) }));
    const lower = forecast.map((point, index) => ({ x: x(junction + 1 + index), y: y(point.lower) })).reverse();
    const bandPath = forecast.length > 0 ? `${polyline([anchor, ...upper, ...lower])} Z` : "";

    return { x, y, plotWidth, junction, anchor, historyPath, forecastPath, bandPath, ticks: niceTicks(min, max) };
  }, [forecast, shown, width]);

  const total = shown.length + forecast.length;
  const lastForecast = forecast[forecast.length - 1];

  const scrub = (event: GestureResponderEvent) => {
    if (!geometry || total < 2) return;
    const ratio = Math.min(Math.max(event.nativeEvent.locationX / geometry.plotWidth, 0), 1);
    setActive(Math.round(ratio * (total - 1)));
  };

  // The readout leads with the value; without a touch it shows the end of the forecast.
  const readoutIndex = active ?? total - 1;
  const readout =
    readoutIndex < shown.length
      ? { date: shown[readoutIndex].date, value: shown[readoutIndex].close, label: "close", range: null }
      : (() => {
          const point = forecast[readoutIndex - shown.length];
          return { date: point.date, value: point.predicted, label: "forecast", range: [point.lower, point.upper] };
        })();

  const activePoint =
    geometry && active !== null
      ? active < shown.length
        ? { x: geometry.x(active), y: geometry.y(shown[active].close), color: colors.chartHistory }
        : {
            x: geometry.x(active),
            y: geometry.y(forecast[active - shown.length].predicted),
            color: colors.chartForecast,
          }
      : null;

  const accessibilityLabel = lastForecast
    ? `Price chart. Last close ${formatPrice(shown[shown.length - 1]?.close ?? 0, currency)}. ` +
      `Forecast for ${formatDate(lastForecast.date, true)}: ${formatPrice(lastForecast.predicted, currency)}, ` +
      `range ${formatPrice(lastForecast.lower, currency)} to ${formatPrice(lastForecast.upper, currency)}. ` +
      "The same values are in the table below."
    : "Price chart of recent closes.";

  return (
    <View style={styles.figure}>
      <Text style={styles.title} accessibilityRole="header">
        Price path
      </Text>
      <Text style={styles.subtitle}>Daily closes and the {horizonDays}-day forecast</Text>

      <View style={styles.controls}>
        <View style={styles.legend}>
          <View style={styles.legendItem}>
            <View style={[styles.keyLine, { borderTopColor: colors.chartHistory }]} />
            <Text style={styles.legendText}>Daily close</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={styles.keyDashes}>
              <View style={[styles.keyDash, { backgroundColor: colors.chartForecast }]} />
              <View style={[styles.keyDash, { backgroundColor: colors.chartForecast }]} />
            </View>
            <Text style={styles.legendText}>Forecast</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.keyBand, { backgroundColor: colors.chartBand }]} />
            <Text style={styles.legendText}>Range</Text>
          </View>
        </View>
        <TextToggle
          options={RANGES}
          value={range}
          labels={RANGE_LABELS}
          onChange={(next) => {
            setActive(null);
            setRange(next);
          }}
          accessibilityLabel="History shown"
          size="small"
        />
      </View>

      <View style={styles.readout}>
        <Text style={styles.readoutValue}>{formatPrice(readout.value, currency)}</Text>
        <Text style={styles.readoutLabel}>
          {readout.label} · {formatDate(readout.date, true)}
        </Text>
        {readout.range ? (
          <Text style={styles.readoutRange}>
            range {formatPrice(readout.range[0], currency)} – {formatPrice(readout.range[1], currency)}
          </Text>
        ) : null}
      </View>

      <View
        style={styles.plot}
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        accessible
        accessibilityRole="image"
        accessibilityLabel={accessibilityLabel}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={scrub}
        onResponderMove={scrub}
        onResponderRelease={() => setActive(null)}
        onResponderTerminate={() => setActive(null)}
        onResponderTerminationRequest={() => true}
      >
        {geometry ? (
          <Svg width={width} height={CHART_HEIGHT} pointerEvents="none">
            {geometry.ticks.map((tick) => (
              <React.Fragment key={tick}>
                <Line
                  x1={0}
                  x2={geometry.plotWidth}
                  y1={geometry.y(tick)}
                  y2={geometry.y(tick)}
                  stroke={colors.grid}
                  strokeWidth={1}
                />
                <SvgText
                  x={width}
                  y={geometry.y(tick) + 4}
                  fill={colors.ink3}
                  fontSize={11}
                  fontFamily={fonts.sans}
                  textAnchor="end"
                >
                  {formatAxisPrice(tick, currency)}
                </SvgText>
              </React.Fragment>
            ))}
            {geometry.bandPath ? <Path d={geometry.bandPath} fill={colors.chartBand} /> : null}
            <Line
              x1={geometry.anchor.x}
              x2={geometry.anchor.x}
              y1={PAD_TOP}
              y2={CHART_HEIGHT - PAD_BOTTOM}
              stroke={colors.rule}
              strokeWidth={1}
            />
            <Path
              d={geometry.historyPath}
              stroke={colors.chartHistory}
              strokeWidth={1.75}
              strokeLinejoin="round"
              strokeLinecap="round"
              fill="none"
            />
            {forecast.length > 0 ? (
              <Path
                d={geometry.forecastPath}
                stroke={colors.chartForecast}
                strokeWidth={2}
                strokeDasharray="5 4"
                strokeLinejoin="round"
                fill="none"
              />
            ) : null}
            {activePoint ? (
              <>
                <Line
                  x1={activePoint.x}
                  x2={activePoint.x}
                  y1={PAD_TOP}
                  y2={CHART_HEIGHT - PAD_BOTTOM}
                  stroke={colors.ink3}
                  strokeWidth={1}
                />
                <Circle cx={activePoint.x} cy={activePoint.y} r={4} fill={activePoint.color} stroke={colors.surface} strokeWidth={2} />
              </>
            ) : null}
            <SvgText x={0} y={CHART_HEIGHT - 6} fill={colors.ink3} fontSize={11} fontFamily={fonts.sans}>
              {formatDate(shown[0].date)}
            </SvgText>
            {geometry.anchor.x > 56 && geometry.plotWidth - geometry.anchor.x > 56 ? (
              <SvgText
                x={geometry.anchor.x}
                y={CHART_HEIGHT - 6}
                fill={colors.ink3}
                fontSize={11}
                fontFamily={fonts.sans}
                textAnchor="middle"
              >
                {formatDate(shown[geometry.junction].date)}
              </SvgText>
            ) : null}
            {lastForecast ? (
              <SvgText
                x={geometry.plotWidth}
                y={CHART_HEIGHT - 6}
                fill={colors.ink3}
                fontSize={11}
                fontFamily={fonts.sans}
                textAnchor="end"
              >
                {formatDate(lastForecast.date)}
              </SvgText>
            ) : null}
          </Svg>
        ) : null}
      </View>
      <Text style={styles.hint}>Touch and drag across the chart to read a single day.</Text>
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  figure: {
    gap: theme.space.xs,
  },
  title: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
  },
  subtitle: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
  controls: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    rowGap: theme.space.xs,
    columnGap: theme.space.lg,
    marginTop: theme.space.sm,
  },
  legend: {
    flexDirection: "row",
    flexWrap: "wrap",
    columnGap: theme.space.lg,
    rowGap: theme.space.xs,
  },
  legendItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  legendText: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  keyLine: {
    width: 18,
    borderTopWidth: 2,
  },
  keyDashes: {
    width: 18,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  keyDash: {
    width: 7,
    height: 2,
  },
  keyBand: {
    width: 18,
    height: 10,
  },
  readout: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "baseline",
    columnGap: theme.space.sm,
    marginTop: theme.space.md,
    minHeight: 24,
  },
  readoutValue: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansSemiBold,
    color: theme.colors.ink,
    fontVariant: ["tabular-nums"],
  },
  readoutLabel: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
  },
  readoutRange: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
    fontVariant: ["tabular-nums"],
  },
  plot: {
    height: CHART_HEIGHT,
    marginTop: theme.space.xs,
  },
  hint: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink3,
  },
}));
