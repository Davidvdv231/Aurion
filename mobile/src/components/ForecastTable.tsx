import React, { useState } from "react";
import { Pressable, Text, View } from "react-native";

import type { ForecastPoint } from "@/api/types";
import { makeStyles } from "@/theme/theme";
import { formatDate, formatPrice } from "@/utils/format";

// The chart's numbers as a table, for screen readers and for anyone who wants exact values.
export function ForecastTable({ forecast, currency }: { forecast: ForecastPoint[]; currency: string }) {
  const styles = useStyles();
  const [open, setOpen] = useState(false);

  return (
    <View>
      <Pressable
        onPress={() => setOpen((value) => !value)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        hitSlop={8}
        style={styles.toggle}
      >
        <Text style={styles.toggleText}>{open ? "Hide the table" : "Show the forecast as a table"}</Text>
      </Pressable>
      {open ? (
        <View style={styles.table}>
          <View style={styles.row}>
            <Text style={[styles.head, styles.dateCell]}>Date</Text>
            <Text style={[styles.head, styles.cell]}>Forecast</Text>
            <Text style={[styles.head, styles.cell]}>Low</Text>
            <Text style={[styles.head, styles.cell]}>High</Text>
          </View>
          {forecast.map((point) => (
            <View key={point.date} style={styles.row}>
              <Text style={[styles.value, styles.dateCell]}>{formatDate(point.date)}</Text>
              <Text style={[styles.value, styles.cell]}>{formatPrice(point.predicted, currency)}</Text>
              <Text style={[styles.value, styles.cell]}>{formatPrice(point.lower, currency)}</Text>
              <Text style={[styles.value, styles.cell]}>{formatPrice(point.upper, currency)}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  toggle: {
    alignSelf: "flex-start",
    paddingVertical: theme.space.xs,
  },
  toggleText: {
    ...theme.text.small,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink2,
    textDecorationLine: "underline",
    textDecorationColor: theme.colors.rule,
  },
  table: {
    marginTop: theme.space.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.ink,
  },
  row: {
    flexDirection: "row",
    gap: theme.space.sm,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.grid,
  },
  dateCell: {
    width: 56,
  },
  cell: {
    flex: 1,
    textAlign: "right",
  },
  head: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink3,
  },
  value: {
    ...theme.text.fine,
    fontFamily: theme.fonts.sans,
    color: theme.colors.ink,
    fontVariant: ["tabular-nums"],
  },
}));
