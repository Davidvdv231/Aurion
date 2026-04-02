import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme/theme";

interface TrendChipProps {
  trend: "bullish" | "bearish" | "neutral";
}

export function TrendChip({ trend }: TrendChipProps) {
  return (
    <View style={[styles.chip, toneStyles[trend]]}>
      <Text style={styles.text}>{trend}</Text>
    </View>
  );
}

const toneStyles = StyleSheet.create({
  bullish: { backgroundColor: theme.colors.successSoft },
  bearish: { backgroundColor: theme.colors.dangerSoft },
  neutral: { backgroundColor: theme.colors.warningSoft },
});

const styles = StyleSheet.create({
  chip: {
    alignSelf: "flex-start",
    paddingHorizontal: theme.space.sm,
    paddingVertical: 6,
    borderRadius: 999,
  },
  text: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.xs,
    fontWeight: "800",
    textTransform: "uppercase",
  },
});

