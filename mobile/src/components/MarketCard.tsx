import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme/theme";

interface MarketCardProps {
  symbol: string;
  name: string;
  price: string;
  change: string;
  confidence: string;
  tone: "bullish" | "bearish" | "neutral";
  onPress: () => void;
}

export function MarketCard({ symbol, name, price, change, confidence, tone, onPress }: MarketCardProps) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.headerRow}>
        <Text style={styles.symbol}>{symbol}</Text>
        <Text style={[styles.badge, toneStyles[tone]]}>{tone}</Text>
      </View>
      <Text style={styles.name}>{name}</Text>
      <Text style={styles.price}>{price}</Text>
      <View style={styles.footerRow}>
        <Text style={styles.change}>{change}</Text>
        <Text style={styles.confidence}>{confidence}</Text>
      </View>
    </Pressable>
  );
}

const toneStyles = StyleSheet.create({
  bullish: { color: theme.colors.success },
  bearish: { color: theme.colors.danger },
  neutral: { color: theme.colors.warning },
});

const styles = StyleSheet.create({
  card: {
    width: 190,
    padding: theme.space.md,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: theme.space.sm,
  },
  pressed: {
    transform: [{ scale: 0.98 }],
    opacity: 0.92,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  symbol: {
    color: theme.colors.textPrimary,
    fontWeight: "800",
    fontSize: theme.fontSizes.lg,
  },
  badge: {
    fontSize: theme.fontSizes.xs,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  name: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
  price: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.xl,
    fontWeight: "800",
  },
  footerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  change: {
    color: theme.colors.textPrimary,
    fontSize: theme.fontSizes.sm,
    fontWeight: "700",
  },
  confidence: {
    color: theme.colors.textMuted,
    fontSize: theme.fontSizes.sm,
  },
});

