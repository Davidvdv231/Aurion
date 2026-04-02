import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme/theme";

interface ForecastCardProps {
  date: string;
  predicted: number;
  lower: number;
  upper: number;
}

export function ForecastCard({ date, predicted, lower, upper }: ForecastCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.date}>{date}</Text>
      <Text style={styles.price}>{predicted.toFixed(2)}</Text>
      <Text style={styles.band}>
        Range {lower.toFixed(2)} - {upper.toFixed(2)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    minWidth: 120,
    padding: theme.space.md,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: theme.space.xs,
  },
  date: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    fontWeight: "600",
  },
  price: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.lg,
    fontWeight: "800",
  },
  band: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
  },
});

