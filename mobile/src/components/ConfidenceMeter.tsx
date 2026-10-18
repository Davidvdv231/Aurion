import React from "react";
import { Text, View } from "react-native";

import type { ConfidenceTier } from "@/api/types";
import { makeStyles } from "@/theme/theme";

const TIER_LEVELS: Record<ConfidenceTier, number> = { low: 1, medium: 2, high: 3 };
const TIER_LABELS: Record<ConfidenceTier, string> = { low: "Low", medium: "Medium", high: "High" };

// Three blocks and a word, the same reading as the web app's facts list.
export function ConfidenceMeter({ tier }: { tier: ConfidenceTier }) {
  const styles = useStyles();
  const level = TIER_LEVELS[tier] ?? 1;
  return (
    <View style={styles.row}>
      <View style={styles.meter} aria-hidden>
        {[1, 2, 3].map((step) => (
          <View key={step} style={[styles.block, step <= level && styles.filled]} />
        ))}
      </View>
      <Text style={styles.value}>{TIER_LABELS[tier] ?? tier}</Text>
    </View>
  );
}

const useStyles = makeStyles((theme) => ({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  meter: {
    flexDirection: "row",
    gap: 2,
  },
  block: {
    width: 16,
    height: 8,
    backgroundColor: theme.colors.grid,
  },
  filled: {
    backgroundColor: theme.colors.ink2,
  },
  value: {
    ...theme.text.body,
    fontFamily: theme.fonts.sansMedium,
    color: theme.colors.ink,
  },
}));
