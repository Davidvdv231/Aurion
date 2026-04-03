import React from "react";
import { type DimensionValue, StyleSheet, Text, View } from "react-native";

import type { ConfidenceTier } from "@/api/types";
import { theme } from "@/theme/theme";

interface ConfidenceMeterProps {
  tier: ConfidenceTier;
  degraded?: boolean;
}

const tierWidths: Record<ConfidenceTier, DimensionValue> = {
  low: "30%",
  medium: "60%",
  high: "90%",
};

const tierLabels: Record<ConfidenceTier, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export function ConfidenceMeter({ tier, degraded = false }: ConfidenceMeterProps) {
  const caption = degraded
    ? "Fallback conditions applied. Confidence tier reflects forecast band width and validation quality."
    : "Confidence tier reflects forecast band width and validation quality.";

  return (
    <View style={styles.container}>
      <View style={styles.labelRow}>
        <Text style={styles.label}>Confidence</Text>
        <Text style={styles.value}>{tierLabels[tier]}</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: tierWidths[tier] }]} />
      </View>
      <Text style={styles.caption}>{caption}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.space.sm,
  },
  labelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
    fontWeight: "600",
  },
  value: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.sm,
    fontWeight: "700",
  },
  track: {
    height: 10,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceElevated,
    overflow: "hidden",
  },
  fill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: theme.colors.accent,
  },
  caption: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.xs,
    lineHeight: 18,
  },
});
